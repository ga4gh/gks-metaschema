#!/usr/bin/env python3
"""convert yaml on stdin to json on stdout"""
import copy
import json
import yaml
import re
from pathlib import Path

SCHEMA_DEF_KEYWORD_BY_VERSION = {
    "http://json-schema.org/draft-07/schema": "definitions",
    "http://json-schema.org/draft/2020-12/schema": "$defs"
}


ref_re = re.compile(r':ref:`(.*?)(\s?<.*>)?`')
link_re = re.compile(r'`(.*?)\s?\<(.*)\>`_')
curie_re = re.compile(r'(\S+):(\S+)')
defs_re = re.compile(r'#/(\$defs|definitions)/.*')


class YamlSchemaProcessor:

    def __init__(self, schema_fp, imported=False):
        self.schema_fp = Path(schema_fp)
        self.imported = imported
        self.raw_schema = self.load_schema(schema_fp)
        self.schema_def_keyword = SCHEMA_DEF_KEYWORD_BY_VERSION[self.raw_schema['$schema']]
        self.raw_defs = self.raw_schema.get(self.schema_def_keyword, None)
        self.imports = dict()
        self.import_dependencies()
        self.strict = self.raw_schema.get('strict', False)
        self.enforce_ordered = self.raw_schema.get('enforce_ordered', self.strict)
        self._init_from_raw()

    def _init_from_raw(self):
        self.has_children = self.build_raw_ref_dict()
        self.processed_schema = copy.deepcopy(self.raw_schema)
        self.defs = self.processed_schema.get(self.schema_def_keyword, None)
        self.processed_classes = set()
        self.process_schema()
        self.for_js = copy.deepcopy(self.processed_schema)
        self.clean_for_js()

    def build_raw_ref_dict(self):
        class_mapping = dict()
        # For all classes:
        #   If an abstract class, register oneOf enumerations
        #   If it inherits from a class, register the inheritance
        for cls, cls_def in self.raw_defs.items():
            cls_url = f'#/{self.schema_def_keyword}/{cls}'
            if self.class_is_abstract(cls) and 'oneOf' in cls_def:
                maps_to = class_mapping.get(cls_url, set())
                for record in cls_def['oneOf']:
                    if not isinstance(record, dict):
                        continue
                    assert len(record) == 1
                    if '$ref' in record:
                        mapped = record['$ref']
                    elif '$ref_curie' in record:
                        mapped = self.resolve_curie(record['$ref_curie'])
                    maps_to.add(mapped)
                class_mapping[cls_url] = maps_to
            if 'inherits' in cls_def:
                target = cls_def['inherits']
                if ':' in target:
                    continue  # Ignore mappings from definitions in other sources
                target_url = f'#/{self.schema_def_keyword}/{target}'
                maps_to = class_mapping.get(target_url, set())
                maps_to.add(cls_url)
                class_mapping[target_url] = maps_to
        return class_mapping

    def merge_imported(self):
        # register all import namespaces and create process order
        # note: relying on max_recursion_depth errors and not checking for cyclic imports
        self.import_locations = dict()
        self.import_processors = dict()
        self.import_process_order = list()
        self._register_merge_import(self)

        # check that all classes defined in imports are unique
        defined_classes = self.processed_classes
        for key in self.import_process_order:
            other = self.import_processors[key]
            assert len(defined_classes & other.processed_classes) == 0
            defined_classes.update(other.processed_classes)

        for key in self.import_process_order:
            self.raw_schema['namespaces'][key] = f'#/{self.schema_def_keyword}/'
            other = self.import_processors[key]
            other_ns = other.raw_schema.get('namespaces', list())
            if other_ns:
                for ns in other_ns:
                    if ns not in self.import_process_order:
                        # Handle external refs that do not match imports
                        self.raw_schema['namespaces'][key] = other.raw_schema['namespaces'][key]
            self.raw_defs.update(other.raw_defs)

        # revise all class.inherits attributes from CURIE to local defs
        for cls in defined_classes:
            cls_inherits_prop = self.raw_defs[cls].get('inherits', '')
            if curie_re.match(cls_inherits_prop):
                self.raw_defs[cls]['inherits'] = cls_inherits_prop.split(':')[1]

            # check all class.properties match expected definitions style
            self.raw_defs[cls] = self._check_local_defs_property(self.raw_defs[cls])

        # clear imports
        self.imports = dict()

        # update title
        self.raw_schema['title'] = self.raw_schema['title'] + '-Merged-Imports'

        # reprocess raw_schema
        self.raw_defs = self.raw_schema.get(self.schema_def_keyword, None)
        self._init_from_raw()

    def _check_local_defs_property(self, obj):
        try:
            for k, v in obj.items():
                if isinstance(v, dict):
                    obj[k] = self._check_local_defs_property(v)
                elif isinstance(v, list):
                    l = list()
                    for element in v:
                        l.append(self._check_local_defs_property(element))
                    obj[k] = l
                elif isinstance(v, str) and k == "$ref":
                    match = defs_re.match(v)
                    assert match, v
                    if match.group(1) != self.schema_def_keyword:
                        obj[k] = re.sub(re.escape(match.group(1)), self.schema_def_keyword, v)
        except AttributeError:
            return obj
        return obj

    def _register_merge_import(self, proc):
        for name, other in proc.imports.items():
            self._register_merge_import(other)
            if name in self.import_locations:
                # check that all imports from imported point to same locations
                assert self.import_locations[name] == other.schema_fp
            else:
                self.import_locations[name] = other.schema_fp
                self.import_processors[name] = other
                self.import_process_order.append(name)
        return

    @staticmethod
    def load_schema(schema_fp):
        with open(schema_fp) as f:
            schema = yaml.load(f, Loader=yaml.SafeLoader)
        return schema

    def import_dependencies(self):
        for dependency in self.raw_schema.get('imports', list()):
            fp = Path(self.raw_schema['imports'][dependency])
            if not fp.is_absolute():
                base_path = self.schema_fp.parent
                fp = base_path.joinpath(fp)
            self.imports[dependency] = YamlSchemaProcessor(fp, imported=True)

    def process_schema(self):
        if self.defs is None:
            return

        for schema_class in self.defs:
            self.process_schema_class(schema_class)

    def class_is_abstract(self, schema_class):
        schema_class_def, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        return 'properties' not in schema_class_def and not self.class_is_primitive(schema_class)

    def class_is_passthrough(self, schema_class):
        if not self.class_is_abstract(schema_class):
            return False
        raw_class_definition = self.get_local_or_inherited_class(schema_class, raw=True)
        if 'heritable_properties' not in raw_class_definition \
                and 'properties' not in raw_class_definition \
                and raw_class_definition[0].get('inherits'):
            return True
        return False

    def class_is_primitive(self, schema_class):
        schema_class_def, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        schema_class_type = schema_class_def.get('type', 'abstract')
        if schema_class_type not in ['abstract', 'object']:
            return True
        return False

    def js_json_dump(self, stream):
        json.dump(self.for_js, stream, indent=3, sort_keys=False)

    def js_yaml_dump(self, stream):
        yaml.dump(self.for_js, stream, sort_keys=False)

    def resolve_curie(self, curie):
        namespace, identifier = curie.split(':')
        base_url = self.processed_schema['namespaces'][namespace]
        return base_url + identifier

    def process_property_tree_refs(self, raw_node, processed_node):
        if isinstance(raw_node, dict):
            for k, v in raw_node.items():
                if k.endswith('_curie'):
                    new_k = k[:-6]
                    processed_node[new_k] = self.resolve_curie(v)
                    del (processed_node[k])
                elif k == '$ref' and v.startswith('#/') and self.imported:
                    # TODO: fix below hard-coded name convention, yuck.
                    processed_node[k] = str(self.schema_fp.stem.split('-')[0]) + '.json' + v
                else:
                    self.process_property_tree_refs(raw_node[k], processed_node[k])
        elif isinstance(raw_node, list):
            for raw_item, processed_item in zip(raw_node, processed_node):
                self.process_property_tree_refs(raw_item, processed_item)
        return

    def get_local_or_inherited_class(self, schema_class, raw=False):
        components = schema_class.split(':')
        if len(components) == 1:
            inherited_class_name = components[0]
            if raw:
                inherited_class = self.raw_schema[self.schema_def_keyword][inherited_class_name]
            else:
                self.process_schema_class(inherited_class_name)
                inherited_class = self.processed_schema[self.schema_def_keyword][inherited_class_name]
            proc = self
        elif len(components) == 2:
            inherited_class_name = components[1]
            proc = self.imports[components[0]]
            if raw:
                inherited_class = \
                    proc.raw_schema[proc.schema_def_keyword][inherited_class_name]
            else:
                inherited_class = \
                    proc.processed_schema[proc.schema_def_keyword][inherited_class_name]
        else:
            raise ValueError
        return inherited_class, proc

    def process_schema_class(self, schema_class):
        raw_class_def = self.raw_schema[self.schema_def_keyword][schema_class]
        if schema_class in self.processed_classes:
            return
        if self.class_is_primitive(schema_class):
            self.processed_classes.add(schema_class)
            return
        processed_class_def = self.processed_schema[self.schema_def_keyword][schema_class]
        inherited_properties = dict()
        inherited_required = set()
        inherits = processed_class_def.get('inherits', None)
        if inherits is not None:
            inherited_class, proc = self.get_local_or_inherited_class(inherits)
            # extract properties / heritable_properties and required / heritable_required from inherited_class
            # currently assumes inheritance from abstract classes only–will break otherwise
            inherited_properties |= copy.deepcopy(inherited_class['heritable_properties'])
            inherited_required |= set(inherited_class.get('heritable_required', list()))

        if self.class_is_abstract(schema_class):
            prop_k = 'heritable_properties'
            req_k = 'heritable_required'
        else:
            prop_k = 'properties'
            req_k = 'required'
        raw_class_properties = raw_class_def.get(prop_k, dict())  # Nested inheritance!
        processed_class_properties = processed_class_def.get(prop_k, dict())
        processed_class_required = set(processed_class_def.get(req_k, []))
        # Process refs
        self.process_property_tree_refs(raw_class_properties, processed_class_properties)

        for prop, prop_attribs in processed_class_properties.items():
            # Mix in inherited properties
            if 'extends' in prop_attribs:
                # assert that the extended property is in inherited properties
                assert prop_attribs['extends'] in inherited_properties
                extended_property = prop_attribs['extends']
                # fix $ref and oneOf $ref inheritance
                if "$ref" in prop_attribs:
                    if 'oneOf' in inherited_properties[extended_property]:
                        inherited_properties[extended_property].pop("oneOf")
                    elif 'anyOf' in inherited_properties[extended_property]:
                        inherited_properties[extended_property].pop("anyOf")
                if "oneOf" in prop_attribs or "anyOf" in prop_attribs:
                    if "$ref" in inherited_properties[extended_property]:
                        inherited_properties[extended_property].pop("$ref")
                # merge and clean up inherited properties
                processed_class_properties[prop] = inherited_properties[extended_property]
                processed_class_properties[prop].update(prop_attribs)
                processed_class_properties[prop].pop('extends')
                inherited_properties.pop(extended_property)
                # update required field
                if extended_property in inherited_required:
                    inherited_required.remove(extended_property)
                    processed_class_required.add(prop)
            # Validate required array attribute for GKS specs
            if self.enforce_ordered and prop_attribs.get('type', '') == 'array':
                assert 'ordered' in prop_attribs, f'{schema_class}.{prop} missing ordered attribute.'
                assert isinstance(prop_attribs['ordered'], bool)

        processed_class_def[prop_k] = inherited_properties | processed_class_properties
        processed_class_def[req_k] = sorted(list(inherited_required | processed_class_required))
        if self.strict and not self.class_is_abstract(schema_class):
            processed_class_def['additionalProperties'] = False
        self.processed_classes.add(schema_class)

    @staticmethod
    def _scrub_rst_markup(string):
        string = ref_re.sub('\g<1>', string)
        string = link_re.sub('[\g<1>](\g<2>)', string)
        string = string.replace('\n', ' ')
        return string

    def clean_for_js(self):
        self.for_js.pop('namespaces', None)
        self.for_js.pop('strict', None)
        self.for_js.pop('enforce_ordered', None)
        self.for_js.pop('imports', None)
        abstract_class_removals = list()
        for schema_class, schema_definition in self.for_js.get(self.schema_def_keyword, dict()).items():
            schema_definition.pop('inherits', None)
            if self.class_is_abstract(schema_class):
                schema_definition.pop('heritable_properties', None)
                schema_definition.pop('heritable_required', None)
                schema_definition.pop('header_level', None)
                if 'oneOf' not in schema_definition:
                    abstract_class_removals.append(schema_class)
            if 'description' in schema_definition:
                schema_definition['description'] = \
                    self._scrub_rst_markup(schema_definition['description'])
            if 'properties' in schema_definition:
                for p, p_def in schema_definition['properties'].items():
                    if 'description' in p_def:
                        p_def['description'] = \
                            self._scrub_rst_markup(p_def['description'])
                    self.concretize_js_object(p_def)

        for cls in abstract_class_removals:
            self.for_js[self.schema_def_keyword].pop(cls)

    def concretize_js_object(self, js_obj):
        if '$ref' in js_obj:
            descendents = self.concretize_class_ref(js_obj['$ref'])
            if descendents != {js_obj['$ref']}:
                js_obj.pop('$ref')
                js_obj['oneOf'] = self._build_ref_list(descendents)
        elif 'oneOf' in js_obj:
            # do the same check for each member
            ref_list = js_obj['oneOf']
            descendents = set()
            for ref in ref_list:
                descendents.update(self.concretize_class_ref(ref['$ref']))
            js_obj['oneOf'] = self._build_ref_list(descendents)
        elif js_obj.get('type', '') == 'array':
            self.concretize_js_object(js_obj['items'])

    def concretize_class_ref(self, cls_url):
        children = self.has_children.get(cls_url, None)
        if children is None:
            return {cls_url}
        out = set()
        for child in children:
            out.update(self.concretize_class_ref(child))
        return out

    @staticmethod
    def _build_ref_list(cls_urls):
        return [{'$ref': url} for url in sorted(cls_urls)]
