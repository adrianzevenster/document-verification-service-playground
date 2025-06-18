from google.cloud import storage
from google.oauth2 import service_account
from google.genai import Client
from .config import Config

_cfg = Config()

def init_clients():
    creds = service_account.Credentials.from_service_account_file(
        _cfg.SA_KEY_PATH, scopes=_cfg.SCOPES
    )
    storage_client = storage.Client(credentials=creds,
                                    project=_cfg.PROJECT_ID)
    genai_client   = Client(
        vertexai=True,
        credentials=creds,
        project=_cfg.PROJECT_ID,
        location=_cfg.LOCATION,
    )
    return storage_client, genai_client, creds
