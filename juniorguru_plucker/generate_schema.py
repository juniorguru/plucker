import argparse
import json
from importlib import import_module
from pathlib import Path


def main(item_class_path: str):
    item_module_path, item_class_name = item_class_path.split(":")
    item_module = import_module(item_module_path)
    item_class = getattr(item_module, item_class_name)

    properties = {
        name: (
            {
                "label": name,
                "format": kwargs.get("apify_format"),
            }
            if kwargs.get("apify_format")
            else {
                "label": name,
            }
        )
        for name, kwargs in item_class.fields.items()
    }

    schema = {
        "title": item_class_name,
        "actorSpecification": 1,
        "views": {
            "titles": {
                "title": item_class_name,
                "transformation": {"fields": list(properties.keys())},
                "display": {
                    "component": "table",
                    "properties": properties,
                },
            }
        },
    }
    # print(json.dumps(schema, indent=2, ensure_ascii=False))

    module_path = Path(item_module.__file__)
    schema_name = item_class_name[0].lower() + item_class_name[1:]
    schema_path = module_path.parent / f"{schema_name}Schema.json"
    schema_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("item_class_path")
    args = parser.parse_args()
    main(args.item_class_path)
