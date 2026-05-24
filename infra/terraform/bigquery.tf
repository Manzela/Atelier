resource "google_bigquery_dataset" "atelier_trajectories" {
  dataset_id  = "atelier_trajectories"
  project     = var.project_id
  location    = "US"
  description = "Atelier trajectory store: session events, DPO pairs, calibration metrics, cost ledger"
}

resource "google_bigquery_table" "trajectory_records" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "trajectory_records"
  deletion_protection = false
  schema = jsonencode([
    { name = "session_id", type = "STRING", mode = "REQUIRED" },
    { name = "tenant_id", type = "STRING", mode = "REQUIRED" },
    { name = "node_name", type = "STRING", mode = "REQUIRED" },
    { name = "phase", type = "STRING", mode = "REQUIRED" },
    { name = "expert_id", type = "STRING", mode = "NULLABLE" },
    { name = "occurred_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "payload", type = "JSON", mode = "NULLABLE" },
    { name = "embedding", type = "FLOAT64", mode = "REPEATED" },
  ])
}

resource "google_bigquery_table" "dpo_preference_pairs" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "dpo_preference_pairs"
  deletion_protection = false
  schema = jsonencode([
    { name = "pair_id", type = "STRING", mode = "REQUIRED" },
    { name = "session_id", type = "STRING", mode = "REQUIRED" },
    { name = "tenant_id", type = "STRING", mode = "REQUIRED" },
    { name = "chosen_output", type = "STRING", mode = "REQUIRED" },
    { name = "rejected_output", type = "STRING", mode = "REQUIRED" },
    { name = "extrinsic_margin", type = "FLOAT64", mode = "REQUIRED" },
    { name = "swap_stability", type = "FLOAT64", mode = "REQUIRED" },
    { name = "kappa_vs_golden", type = "FLOAT64", mode = "REQUIRED" },
    { name = "dpo_eligible", type = "BOOL", mode = "REQUIRED" },
    { name = "failed_checks", type = "STRING", mode = "REPEATED" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "calibration_metrics" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "calibration_metrics"
  deletion_protection = false
  schema = jsonencode([
    { name = "run_id", type = "STRING", mode = "REQUIRED" },
    { name = "judge_model", type = "STRING", mode = "REQUIRED" },
    { name = "axis", type = "STRING", mode = "REQUIRED" },
    { name = "kappa", type = "FLOAT64", mode = "REQUIRED" },
    { name = "sample_size", type = "INT64", mode = "REQUIRED" },
    { name = "measured_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_table" "cost_ledger" {
  dataset_id          = google_bigquery_dataset.atelier_trajectories.dataset_id
  project             = var.project_id
  table_id            = "cost_ledger"
  deletion_protection = false
  schema = jsonencode([
    { name = "session_id", type = "STRING", mode = "REQUIRED" },
    { name = "phase", type = "STRING", mode = "REQUIRED" },
    { name = "expert_id", type = "STRING", mode = "REQUIRED" },
    { name = "input_tokens", type = "INT64", mode = "REQUIRED" },
    { name = "cost_usd", type = "FLOAT64", mode = "REQUIRED" },
    { name = "recorded_at", type = "TIMESTAMP", mode = "REQUIRED" },
  ])
}
