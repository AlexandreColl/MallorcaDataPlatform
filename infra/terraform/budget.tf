# The platform is sized to cost cents (S3, a catalog and pay-per-query Athena; nothing running 24/7). The budget
# makes any surprise visible: an e-mail at 80 % of the actual spend and when the forecast passes 100 %.

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$mallorca-data-platform"]
  }

  dynamic "notification" {
    for_each = length(var.budget_alert_emails) > 0 ? [
      { threshold = 80, type = "ACTUAL" },
      { threshold = 100, type = "FORECASTED" },
    ] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = var.budget_alert_emails
    }
  }
}
