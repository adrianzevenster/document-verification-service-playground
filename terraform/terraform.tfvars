project_id             = "adg-delivery-moniepoint"
members = [
    "user:adrian@adg.io",
    "user:sashlyn@adg.io",
]
service_account_name   = "adg-documentai-sa"
bucket_name            = "adg-delivery-moniepoint-docs-bucket-001"
processor_name         = "OCR-processor"
processor_type         = "OCR_PROCESSOR"
docai_location         = "eu"
gcs_region             = "EU"
notebook_region        = "europe-west1-b"
machine_type           = "n1-standard-4"
workbench_owners       = ["adrian@adg.io"]
notebook_instance_name = "vertex-ai-workbench"
vertex_sa_actors       = ["adrian@adg.io"]