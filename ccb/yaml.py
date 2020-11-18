from ruamel.yaml import YAML
from ruamel.yaml.constructor import DoubleQuotedScalarString

yaml = YAML()
yaml.preserve_quotes = True

DoubleQuotes = DoubleQuotedScalarString
