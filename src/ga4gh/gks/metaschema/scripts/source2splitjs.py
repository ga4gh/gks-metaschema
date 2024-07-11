#!/usr/bin/env python3

from pathlib import Path
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
import argparse
import re
import os
import copy
import json

parser = argparse.ArgumentParser()
parser.add_argument("infile")


def _redirect_refs(obj, dest_path, root_proc, mode):
    frag_re = re.compile(r'(/\$(slot)?defs|definitions)/(\w+)')
    if isinstance(obj, list):
        return [_redirect_refs(x, dest_path, root_proc, mode) for x in obj]
    elif isinstance(obj, dict):
        for k, v in obj.items():
            is_slot = False
            if k == '$ref':
                parts = v.split('#')
                if len(parts) == 2:
                    ref, fragment = parts
                elif len(parts) == 1:
                    ref = parts[0]
                    fragment = ''
                else:
                    raise ValueError(f'Expected only one fragment operator.')
                if fragment:
                    m = frag_re.match(fragment)
                    assert m is not None, fragment
                    ref_class = m.group(3)
                    is_slot = bool(m.group(2))
                    if is_slot:
                        return obj
                else:
                    ref_class = ref.split('/')[-1].split('.')[0]

                # Test if reference is for internal or external object
                # and retrieve appropriate processor for export path
                if ref == '':
                    proc = root_proc
                else:
                    proc = None
                    for _, other in root_proc.imports.items():
                        if is_slot:
                            def_set = other.slot_defs
                        else:
                            def_set = other.defs
                        if ref_class in def_set:
                            proc = other
                            break
                    if proc is None:
                        raise ValueError(f'Could not find {ref_class} in processors')
                # if reference is a slot, return slot path
                if is_slot:
                    pass # TODO: Implement this
                # if reference is protected for the class being processed, return only fragment
                elif ref == '' and proc.class_is_protected(ref_class):
                    containing_class = proc.raw_defs[ref_class]['protectedClassOf']
                    if containing_class == dest_path.name:
                        obj[k] = f'#{fragment}'
                        return obj
                else:
                    obj[k] = proc.get_class_abs_path(ref_class, mode)
            else:
                obj[k] = _redirect_refs(v, dest_path, root_proc, mode)
        return obj
    else:
        return obj


def split_defs_to_js(root_proc, mode='json'):
    if mode == 'json':
        fp = root_proc.json_fp
    elif mode == 'yaml':
        fp = root_proc.yaml_fp
    else:
        raise ValueError('mode must be json or yaml')
    os.makedirs(fp, exist_ok=True)
    kw = root_proc.schema_def_keyword
    for cls in root_proc.for_js[kw].keys():
        if root_proc.class_is_protected(cls):
            continue
        class_def = copy.deepcopy(root_proc.for_js[kw][cls])
        target_path = fp / f'{cls}'
        out_doc = copy.deepcopy(root_proc.for_js)
        if cls in root_proc.has_protected_members:
            def_dict = dict()
            keep = False
            for protected_cls in root_proc.has_protected_members[cls]:
                if root_proc.raw_defs[protected_cls]['protectedClassOf'] == cls:
                    def_dict[protected_cls] = copy.deepcopy(root_proc.defs[protected_cls])
                    keep = True
            if keep:
                out_doc[kw] = _redirect_refs(def_dict, target_path, root_proc, mode)
            else:
                out_doc.pop(kw, None)
        else:
            out_doc.pop(kw, None)
        class_def = _redirect_refs(class_def, target_path, root_proc, mode)
        out_doc.update(class_def)
        out_doc['title'] = cls
        out_doc['$id'] = root_proc.get_class_uri(cls, mode)
        with open(target_path, 'w') as f:
            json.dump(out_doc, f, indent=3, sort_keys=False)


if __name__ == '__main__':
    args = parser.parse_args()
    p = YamlSchemaProcessor(Path(args.infile))
    split_defs_to_js(p)
