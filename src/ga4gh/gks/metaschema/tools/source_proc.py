#!/usr/bin/env python3
"""convert yaml on stdin to json on stdout"""
import copy
import json
import yaml
import re
from pathlib import Path
import os
from collections import defaultdict

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
        self.has_children_urls = dict()
        self.has_children = dict()
        self.build_inheritance_dicts()
        self.has_protected_members = defaultdict(set)
        self.processed_schema = copy.deepcopy(self.raw_schema)
        self.defs = self.processed_schema.get(self.schema_def_keyword, None)
        self.processed_classes = set()
        self.process_schema()
        self.for_js = copy.deepcopy(self.processed_schema)
        self.clean_for_js()

    def build_inheritance_dicts(self):
        # For all classes:
        #   If an abstract class, register oneOf enumerations
        #   If it inherits from a class, register the inheritance
        for cls, cls_def in self.raw_defs.items():
            cls_url = f'#/{self.schema_def_keyword}/{cls}'
            if self.class_is_abstract(cls) and 'oneOf' in cls_def:
                maps_to_urls = self.has_children_urls.get(cls_url, set())
                maps_to = self.has_children.get(cls, set())
                for record in cls_def['oneOf']:
                    if not isinstance(record, dict):
                        continue
                    assert len(record) == 1
                    if '$ref' in record:
                        mapped = record['$ref']
                    elif '$refCurie' in record:
                        mapped = self.resolve_curie(record['$refCurie'])
                    maps_to_urls.add(mapped)
                    maps_to.add(mapped.split('/')[-1])
                self.has_children_urls[cls_url] = maps_to_urls
                self.has_children[cls] = maps_to
            if 'inherits' in cls_def:
                target = cls_def['inherits']
                if ':' in target:
                    continue  # Ignore mappings from definitions in other sources
                target_url = f'#/{self.schema_def_keyword}/{target}'
                maps_to_urls = self.has_children_urls.get(target_url, set())
                maps_to = self.has_children.get(target, set())
                maps_to_urls.add(cls_url)
                maps_to.add(cls)
                self.has_children_urls[target_url] = maps_to_urls
                self.has_children[target] = maps_to

    def get_all_descendants(self, cls):
        out = set()
        for descendant in self.has_children.get(cls, []):
            out.add(descendant)
            out.update(self.get_all_descendants(descendant))
        return out

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

    def class_is_protected(self, schema_class):
        schema_class_def, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        return 'protectedClassOf' in schema_class_def

    def class_is_ga4gh_identifiable(self, schema_class):
        schema_class_def, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        return 'ga4ghDigest' in schema_class_def and 'prefix' in schema_class_def['ga4ghDigest']

    def class_is_passthrough(self, schema_class):
        if not self.class_is_abstract(schema_class):
            return False
        raw_class_definition, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        if 'heritableProperties' not in raw_class_definition \
                and 'properties' not in raw_class_definition \
                and raw_class_definition.get('inherits', False):
            return True
        return False

    def class_is_primitive(self, schema_class):
        schema_class_def, _ = self.get_local_or_inherited_class(schema_class, raw=True)
        schema_class_type = schema_class_def.get('type', 'abstract')
        if schema_class_type not in ['abstract', 'object']:
            return True
        return False

    def class_is_subclass(self, schema_class, parent_class):
        schema_class_fragment = f'#/{self.schema_def_keyword}/{schema_class}'
        parent_class_fragment = f'#/{self.schema_def_keyword}/{parent_class}'
        children = self.concretize_class_ref(parent_class_fragment)
        return schema_class_fragment in children

    def js_json_dump(self, stream):
        json.dump(self.for_js, stream, indent=3, sort_keys=False)

    def js_yaml_dump(self, stream):
        yaml.dump(self.for_js, stream, sort_keys=False)

    def split_defs_to_js(self, fp=None):
        frag_re = re.compile(r'(/\$defs|definitions)/(\w+)')
        def _redirect_refs(obj, dest_path):
            if isinstance(obj, list):
                return [_redirect_refs(x, dest_path) for x in obj]
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    if k == '$ref':
                        try:
                            ref, fragment = v.split('#')
                        except ValueError:
                            raise NotImplementedError
                        if ref == '':
                            if fragment:
                                m = frag_re.match(fragment)
                                assert m is not None
                                fragment_class = m.group(2)
                                if self.class_is_protected(fragment_class):
                                    dest_class = dest_path.stem
                                    frag_containing_class = self.raw_defs[fragment_class]['protectedClassOf']
                                    # containing class matches dest
                                    if frag_containing_class == dest_class:
                                        pass
                                    # containing class does not match dest
                                    else:
                                        obj[k] = f'{frag_containing_class}.json#/{self.schema_def_keyword}/{fragment_class}'
                                else:
                                    obj[k] = f'{fragment_class}.json'
                            else:
                                raise NotImplementedError("No handler for non-fragment references")
                        else:
                            # Only works in Python >= 3.12
                            schema_root = self.schema_fp.parent
                            relative_fp = schema_root.relative_to(dest_path.parent, walk_up=True)
                            obj[k] = str(relative_fp / Path(ref)) + fragment
                    else:
                        obj[k] = _redirect_refs(v, dest_path)
                return obj
            else:
                return obj

        if fp is None:
            fp = self.schema_fp.parent / 'json'
        else:
            assert isinstance(fp, Path)
        if not fp.exists():
            os.mkdir(fp)
        kw = self.schema_def_keyword
        for cls in self.for_js[kw].keys():
            if self.class_is_protected(cls):
                continue
            class_def = copy.deepcopy(self.for_js[kw][cls])
            target_path = fp / f'{cls}.json'
            out_doc = copy.deepcopy(self.for_js)
            if cls in self.has_protected_members:
                def_dict = dict()
                keep = False
                for protected_cls in self.has_protected_members[cls]:
                    if self.raw_defs[protected_cls]['protectedClassOf'] == cls:
                        def_dict[protected_cls] = copy.deepcopy(self.defs[protected_cls])
                        keep = True
                if keep:
                    out_doc[kw] = _redirect_refs(def_dict, target_path)
                else:
                    out_doc.pop(kw, None)
            else:
                out_doc.pop(kw, None)
            class_def = _redirect_refs(class_def, target_path)
            out_doc.update(class_def)
            out_doc['title'] = cls
            with open(target_path, 'w') as f:
                json.dump(out_doc, f, indent=3, sort_keys=False)

    def resolve_curie(self, curie):
        namespace, identifier = curie.split(':')
        base_url = self.processed_schema['namespaces'][namespace]
        return base_url + identifier

    def process_property_tree_refs(self, raw_node, processed_node):
        if isinstance(raw_node, dict):
            for k, v in raw_node.items():
                if k.endswith('Curie'):
                    new_k = k[:-5]
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
        processed_class_def = self.processed_schema[self.schema_def_keyword][schema_class]

        # Check GKS maturity model on all public, concrete classes
        if not (self.class_is_protected(schema_class) or self.class_is_abstract(schema_class)):
            assert 'maturity' in processed_class_def, schema_class
            assert processed_class_def['maturity'] in ['draft', 'trial use', 'normative', 'deprecated'], schema_class

        if self.class_is_protected(schema_class):
            containing_class = self.raw_defs[schema_class]['protectedClassOf']
            self.has_protected_members[containing_class].add(schema_class)
            if containing_class in self.has_children:
                for descendant in self.get_all_descendants(containing_class):
                    self.has_protected_members[descendant].add(schema_class)

        if self.class_is_primitive(schema_class):
            self.processed_classes.add(schema_class)
            return
        inherited_properties = dict()
        inherited_required = set()
        inherits = processed_class_def.get('inherits', None)
        if inherits is not None:
            inherited_class, proc = self.get_local_or_inherited_class(inherits)
            # extract properties / heritableProperties and required / heritableRequired from inherited_class
            # currently assumes inheritance from abstract classes only–will break otherwise
            inherited_properties |= copy.deepcopy(inherited_class['heritableProperties'])
            inherited_required |= set(inherited_class.get('heritableRequired', list()))

            # inherit ga4ghDigest keys
            if 'ga4ghDigest' in processed_class_def or 'ga4ghDigest' in inherited_class:
                if 'ga4ghDigest' not in processed_class_def:
                    assert self.class_is_abstract(schema_class), \
                        f'{schema_class} is missing a defined prefix.'
                    processed_class_def['ga4ghDigest'] = copy.deepcopy(inherited_class['ga4ghDigest'])
                elif 'ga4ghDigest' not in inherited_class:
                    pass
                else:
                    ga4ghDigest_keys = set(inherited_class['ga4ghDigest']['keys'])
                    ga4ghDigest_keys |= set(processed_class_def['ga4ghDigest'].get('keys', list()))
                    processed_class_def['ga4ghDigest']['keys'] = sorted(list(ga4ghDigest_keys))

        if self.class_is_abstract(schema_class):
            prop_k = 'heritableProperties'
            req_k = 'heritableRequired'
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
            if self.strict and prop_attribs.get('type', '') == 'object':
                assert prop_attribs.get('additionalProperties', '') is False, \
                    f'"additionalProperties: false" expected in {schema_class}.{prop}'

        # Validate class structures for GKS specs
        if self.class_is_abstract(schema_class):
            assert 'type' not in processed_class_def, schema_class
        else:
            assert 'type' in processed_class_def, schema_class
            assert processed_class_def['type'] == 'object', schema_class
            if self.class_is_ga4gh_identifiable(schema_class):
                assert isinstance(processed_class_def['ga4ghDigest']['prefix'], str), schema_class
                assert processed_class_def['ga4ghDigest']['prefix'] != '', schema_class
                l = len(processed_class_def['ga4ghDigest']['keys'])
                assert l >= 2, \
                    f'GA4GH identifiable objects are expected to be defined by at least 2 properties, {schema_class} has {l}.'
                assert 'type' in processed_class_def['ga4ghDigest']['keys'], \
                    f'GA4GH identifiable objects are expected to include the class type but not included for {schema_class}.'
                    # Two properites should be `type` and at least one other field

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
            schema_definition.pop('protectedClassOf', None)
            if self.class_is_abstract(schema_class):
                schema_definition.pop('heritableProperties', None)
                schema_definition.pop('heritableRequired', None)
                schema_definition.pop('ga4ghDigest', None)
                schema_definition.pop('header_level', None)
                self.concretize_js_object(schema_definition)
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
            inlined = list()
            for ref in ref_list:
                if '$ref' not in ref:
                    inlined.append(ref)
                else:
                    descendents.update(self.concretize_class_ref(ref['$ref']))
            js_obj['oneOf'] = self._build_ref_list(descendents) + inlined
        elif js_obj.get('type', '') == 'array':
                self.concretize_js_object(js_obj['items'])

    def concretize_class_ref(self, cls_url):
        children = self.has_children_urls.get(cls_url, None)
        if children is None:
            return {cls_url}
        out = set()
        for child in children:
            out.update(self.concretize_class_ref(child))
        return out

    @staticmethod
    def _build_ref_list(cls_urls):
        return [{'$ref': url} for url in sorted(cls_urls)]
