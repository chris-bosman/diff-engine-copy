import json

from distutils.util import strtobool
from db import mongo
from pymongo import ReturnDocument

def generate_diffs(bucket, key):
    drift_doc = {}
    resource_types = mongo.infra_db.list_collection_names()

    for type in resource_types:
        meta_collection = mongo.meta_db[f"{type}-{bucket}/{key}"]
        tf_collection = mongo.svc_db[f"{bucket}/{key}"]
        infra_collection = mongo.infra_db[type]

        resources = meta_collection.find_one({})

        if len(resources['diff_ids']) > 0:
            with open(f"diffs/field_translations/aws_tf/{type}.json", "r") as f:
                field_translation_file = json.load(f)
            for resource_id in resources['diff_ids']:
                svc_doc = tf_collection.find_one({ 'aws_id': resource_id })
                infra_doc = [ doc for doc in infra_collection.find() if resource_id in doc.values() ][0]

                drift_doc = parse_fields(field_translation_file, svc_doc, infra_doc)

        if drift_doc != {}:
            drift_doc['resource_id'] = resource_id

            diff_coll = mongo.diff_db[f"{type}-{bucket}/{key}"]
            upload = diff_coll.find_one_and_replace(
                {"resource_id": resource_id},
                drift_doc,
                return_document=ReturnDocument.AFTER,
                upsert=True
            )

            drift_doc = {}

    return {
        "message": "Successfully generated diffs",
        "status": 200
    }

def parse_fields(translation_file, svc_doc, infra_doc):
    drift_doc = {}

    for svc_attr, infra_attr in translation_file.items():
        if isinstance(infra_doc[infra_attr], list) == False:
            if svc_doc[svc_attr] in ["true", "false"] and bool(strtobool(svc_doc[svc_attr])) == infra_doc[infra_attr]:
                pass
            elif svc_doc[svc_attr] == infra_doc[infra_attr]:
                pass
            else:
                drift_doc['diffs'][infra_attr] = {
                    infra_attr: {
                        "svc_prop": svc_doc[svc_attr],
                        "infra_prop": infra_doc[infra_attr]
                    }
                }

        else:
            if svc_attr == "tags":
                drift_doc = generate_tag_diffs(svc_doc, infra_doc, drift_doc)
            else:
                drift_doc = generate_list_diffs(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc)

    return drift_doc

def generate_list_diffs(svc_doc, svc_attr, infra_doc, infra_attr, drift_doc):
    attr_count = int(svc_doc[f"{svc_attr}.%"])
    if attr_count != len(infra_doc[infra_attr]):
        drift_doc['diffs'] = {}
        drift_doc['diffs'][infra_attr] = {
            f"svc_{svc_attr}_count": int(svc_doc[f"{svc_attr}.%"]),
            f"infra_{svc_attr}_count": len(infra_doc[infra_attr])
        }

    svc_keys = list([ attr.split('.')[1] for attr in svc_doc.keys() if f"{svc_attr}." in attr and attr != f"{svc_attr}.%" ])
    infra_keys = list([ attr for attr in infra_doc[infra_attr] ])
    matched_keys = set(svc_keys).intersection(infra_keys)

    if len(matched_keys) < len(infra_keys):
        for key in svc_keys:
            if key not in infra_keys:
                drift_doc['diffs'][infra_attr][key] = {
                    "svc_prop": svc_doc[f"{svc_attr}.{key}"],
                    "infra_prop": ""
                }

        for key in infra_keys:
            if key not in svc_keys:
                drift_doc['diffs'][infra_attr][key] = {
                    "svc_prop": "",
                    "infra_prop": svc_doc[infra_attr][key]
                }

    for key in matched_keys:
        count = len(infra_doc[infra_attr])
        count_index = count - 1
        infra_value = infra_doc[infra_attr][key]

        while count > 0:
            svc_value = svc_doc[f"{svc_attr}.{key}"]
            if svc_value != infra_value:
                drift_doc['diffs'][infra_attr][key] = {
                    "svc_prop": svc_value,
                    "infra_prop": infra_value
                }

            count_index -= 1

    return drift_doc

def generate_tag_diffs(svc_doc, infra_doc, drift_doc):
    tag_count = int(svc_doc["tags.%"])
    if tag_count != len(infra_doc["Tags"]):
        drift_doc['diffs'] = {}
        drift_doc['diffs']['Tags'] = {
            "svc_tag_count": int(svc_doc["tags.%"]),
            "infra_tag_count": len(infra_doc["Tags"])
        }

    svc_tag_keys = [ attr.split(".")[1] for attr in svc_doc.keys() if "tags." in attr and attr != "tags.%" ]
    infra_tag_keys = [ tag['Key'] for tag in infra_doc['Tags'] ]
    matched_keys = set(svc_tag_keys).intersection(infra_tag_keys)

    if len(matched_keys) < len(infra_tag_keys):
        for svc_key in svc_tag_keys:
            if svc_key not in infra_tag_keys:
                drift_doc['diffs']['Tags'][svc_key] = {
                    "svc_prop": svc_doc[f"tags.{svc_key}"],
                    "infra_prop": ""
                }

        for infra_key in infra_tag_keys:
            if infra_key not in svc_tag_keys:
                drift_doc['diffs']['Tags'][infra_key] = {
                    "svc_prop": "",
                    "infra_prop": [ tag['Value'] for tag in infra_doc['Tags'] if tag['Key'] == infra_key ][0]
                }

    for key in matched_keys:
        tag_count = len(infra_doc['Tags'])
        tag_index = tag_count - 1
        infra_value = [ item['Value'] for item in infra_doc['Tags'] if item['Key'] == key ]

        while tag_count > 0:
            svc_value = svc_doc[f"tags.{key}"]
            if svc_value not in infra_value:
                drift_doc['diffs']['Tags'][key] = {
                    "svc_prop": svc_value,
                    "infra_value": infra_value[0]
                }

            tag_count -= 1
    
    return drift_doc