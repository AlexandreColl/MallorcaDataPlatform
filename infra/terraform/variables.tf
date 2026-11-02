variable "region" {
  description = "AWS region. eu-south-2 (Spain) keeps the data next to its sources."
  type        = string
  default     = "eu-south-2"
}

variable "environment" {
  description = "Environment name, part of every resource name."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "name_prefix" {
  description = "Prefix of every resource name. Bucket names are global, so it includes something unique to the owner."
  type        = string
  default     = "mallorca-data-platform"

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.name_prefix))
    error_message = "name_prefix is 3-40 lowercase letters, digits and hyphens."
  }
}

variable "pipeline_trusted_arns" {
  description = "Principals allowed to assume the pipeline and analyst roles. Empty: the account itself (its IAM decides)."
  type        = list(string)
  default     = []
}

variable "bronze_noncurrent_days" {
  description = "Days a replaced raw response is kept in bronze before it expires."
  type        = number
  default     = 90
}

variable "athena_results_days" {
  description = "Days Athena query results are kept."
  type        = number
  default     = 7
}

variable "athena_bytes_scanned_cutoff" {
  description = "Largest scan a single Athena query may do, in bytes (a cost guard: 1 GB is about 0.5 cents)."
  type        = number
  default     = 1073741824

  validation {
    condition     = var.athena_bytes_scanned_cutoff >= 10485760
    error_message = "Athena needs a cutoff of at least 10 MB."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget of the project, in USD. The platform is sized to cost cents."
  type        = number
  default     = 2

  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "monthly_budget_usd must be positive."
  }
}

variable "budget_alert_emails" {
  description = "Who gets the budget alerts (80 % spent, 100 % forecast). Empty: the budget exists without alerts."
  type        = list(string)
  default     = []
}

variable "force_destroy" {
  description = "Let `terraform destroy` delete buckets that still hold data (throwaway demo environments only)."
  type        = bool
  default     = false
}
