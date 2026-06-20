<?php
session_start();
include "config.php";
include "ai_service.php";

if (!isset($_SESSION["user_id"])) {
    header("Location: login.html");
    exit;
}

$userId = (int) $_SESSION["user_id"];
$fileName = $_POST["file"] ?? "";

if ($fileName === "") {
    $_SESSION["flash_success"] = "No PDF was selected for refresh.";
    header("Location: dashboard.php");
    exit;
}

$check = $conn->prepare("SELECT file_name FROM ai_results WHERE user_id = ? AND file_name = ? LIMIT 1");
$check->bind_param("is", $userId, $fileName);
$check->execute();

if (!$check->get_result()->fetch_assoc()) {
    $_SESSION["flash_success"] = "That PDF could not be found in your library.";
    header("Location: dashboard.php");
    exit;
}

$aiError = "";
$result = ai_post("/analyze", ["file_path" => $fileName], 120, $aiError);

if ($result === null) {
    $_SESSION["flash_success"] = "Refresh failed: " . $aiError;
    header("Location: dashboard.php");
    exit;
}

$studyHours = max(1, (int) ($result["study_hours"] ?? 1));
$difficulty = (string) ($result["difficulty"] ?? "Medium");
$summary = (string) ($result["summary"] ?? "No summary was returned.");
$studyPlan = (string) ($result["study_plan"] ?? "Review the PDF in focused sessions and test yourself after each pass.");

$update = $conn->prepare(
    "UPDATE ai_results
     SET study_hours = ?, difficulty = ?, summary = ?, study_plan = ?
     WHERE user_id = ? AND file_name = ?"
);
$update->bind_param("isssis", $studyHours, $difficulty, $summary, $studyPlan, $userId, $fileName);
$update->execute();

$_SESSION["flash_success"] = "Summary refreshed with the latest AI logic.";
header("Location: dashboard.php");
exit;
?>
