import urllib.request
import tempfile

def construct_url(spec):
    return f"https://raw.githubusercontent.com/{spec["org"]}/{spec["repo"]}/{spec["sha"]}/{spec["path"]}"

def retrieve_import(spec):
    url = construct_url(spec)
    response = urllib.request.urlopen(url)
    with tempfile.NamedTemporaryFile(delete=False) as t:
        t.write(response.read())
    return t.name

## Leaving 'Rich' comments:

# test_spec = {"org":"clingen-data-model",
#              "repo":"gks-metaschema",
#              "path":"tests/data/vrs/vrs.yaml",
#              "sha":"fe2995181d06896f567f81ca4550b3b02830b1e5"}

# path = retrieve_import(test_spec)

# print(path)

