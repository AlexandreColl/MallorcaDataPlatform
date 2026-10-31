variable "name" {
  description = "Globally unique bucket name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.name))
    error_message = "S3 bucket names are 3-63 lowercase letters, digits, dots and hyphens."
  }
}

variable "versioning" {
  description = "Keep previous versions of every object (bronze: a re-run never loses the raw response)."
  type        = bool
  default     = true
}

variable "noncurrent_version_days" {
  description = "Days a previous version is kept before it expires (only with versioning)."
  type        = number
  default     = 90

  validation {
    condition     = var.noncurrent_version_days >= 1
    error_message = "noncurrent_version_days must be at least 1."
  }
}

variable "expiration_days" {
  description = "Delete objects this many days after creation (temporary data such as query results). null keeps them."
  type        = number
  default     = null
}

variable "force_destroy" {
  description = "Allow `terraform destroy` to delete a bucket that still has objects (only for throwaway environments)."
  type        = bool
  default     = false
}
