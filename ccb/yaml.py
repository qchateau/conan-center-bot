from ruamel.yaml import YAML
from ruamel.yaml.constructor import DoubleQuotedScalarString

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)

DoubleQuotes = DoubleQuotedScalarString
