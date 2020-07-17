from meta import diff_docs

def generate_docs(bucket, key):
    diff_docs.document_tf_resources(bucket, key)