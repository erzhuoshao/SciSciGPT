from google.cloud import storage
from urllib.parse import quote
import os

def upload_file_to_gcp(local_path: str, gcp_path=None, gcs_bucket_name: str=os.environ.get("GCS_BUCKET_NAME")):
    if gcp_path is None:
        # Mirror the path relative to the local storage root (e.g.
        # session-<id>/<file>) so bucket URLs stay a prefix-swap of local
        # paths and sessions cannot collide on identical filenames.
        root = os.environ.get("LOCAL_STORAGE_PATH")
        gcp_path = None
        if root:
            try:
                rel = os.path.relpath(os.path.abspath(local_path), os.path.abspath(root))
                if not rel.startswith(".."):
                    gcp_path = rel
            except ValueError:
                pass
        if gcp_path is None:
            gcp_path = os.path.basename(local_path)

    # When LOCAL_STORAGE_PATH is a gcsfuse mount of the bucket itself
    # (GCS_WORKSPACE_MOUNTED=true), the file already lives at gcp_path in the
    # bucket, so uploading again is redundant: just return its public URL.
    if os.environ.get("GCS_WORKSPACE_MOUNTED", "").lower() in ("1", "true"):
        bucket_url = os.environ.get("GCS_BUCKET_URL", f"https://storage.googleapis.com/{gcs_bucket_name}")
        return f"{bucket_url.rstrip('/')}/{quote(gcp_path)}"

    client = storage.Client()
    bucket = client.bucket(gcs_bucket_name)

    blob = bucket.blob(gcp_path)
    blob.upload_from_filename(local_path)
    public_url = blob.public_url
    return public_url