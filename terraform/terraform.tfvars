project_id              = "docauth-id"
region                  = "eu-west-1"
bucket_name             = "adg-delivery-moniepoint-docs-bucket"
processor_name          = "document-processor"
processor_type          = "OCR_PROCESSOR"
service_account_name    = "adg-documentai-sa"
members = [
    "user:adrian@adg.io",
    "user:sashlyn@adg.io",
    "serviceAccount: my-sa@docauth-id.iam.gserviceaccount.com",]