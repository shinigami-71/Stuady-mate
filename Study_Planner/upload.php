<?php
session_start();
include "config.php";
include "ai_service.php";

function render_upload_message($title, $message)
{
    $safeTitle = htmlspecialchars($title, ENT_QUOTES, "UTF-8");
    $safeMessage = htmlspecialchars($message, ENT_QUOTES, "UTF-8");

    echo "<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Upload Status</title>
    <link rel=\"stylesheet\" href=\"style.css\">
</head>
<body class=\"auth-page\">
    <main class=\"auth-card status-card\">
        <span class=\"eyebrow\">Upload status</span>
        <h1>{$safeTitle}</h1>
        <p>{$safeMessage}</p>
        <div class=\"form-actions\">
            <a class=\"button-link\" href=\"upload.html\">Try Again</a>
            <a class=\"button-link button-link-secondary\" href=\"dashboard.php\">Dashboard</a>
        </div>
    </main>
</body>
</html>";
    exit;
}

if (!isset($_SESSION["user_id"])) {
    header("Location: login.html");
    exit;
}

if ($_SERVER["REQUEST_METHOD"] !== "POST" || !isset($_FILES["file"])) {
    render_upload_message("No file selected", "Please choose a PDF file before uploading.");
}

$user_id = (int) $_SESSION["user_id"];
$file = $_FILES["file"];

if ($file["error"] !== UPLOAD_ERR_OK) {
    render_upload_message("Upload failed", "The file could not be uploaded. Please try again.");
}

if ($file["size"] > 25 * 1024 * 1024) {
    render_upload_message("File too large", "Please upload a PDF under 25 MB.");
}

$extension = strtolower(pathinfo($file["name"], PATHINFO_EXTENSION));

if ($extension !== "pdf") {
    render_upload_message("PDF required", "Study Planner currently analyzes PDF files only.");
}

$uploadDir = __DIR__ . DIRECTORY_SEPARATOR . "uploads";

if (!is_dir($uploadDir)) {
    mkdir($uploadDir, 0755, true);
}

$nameOnly = pathinfo($file["name"], PATHINFO_FILENAME);
$nameOnly = preg_replace("/[^A-Za-z0-9._-]/", "_", $nameOnly);
$nameOnly = trim($nameOnly, "._-");

if ($nameOnly === "") {
    $nameOnly = "study_file";
}

$safeName = "user{$user_id}_" . date("Ymd_His") . "_" . bin2hex(random_bytes(3)) . "_{$nameOnly}.pdf";
$targetPath = $uploadDir . DIRECTORY_SEPARATOR . $safeName;

if (!move_uploaded_file($file["tmp_name"], $targetPath)) {
    render_upload_message("Upload failed", "The file could not be saved. Please try again.");
}

$aiError = "";
$result = ai_post("/analyze", ["file_path" => $safeName], 120, $aiError);

if ($result === null) {
    render_upload_message("AI service unavailable", "The PDF was uploaded, but analysis could not finish. " . $aiError);
}

$studyHours = max(1, (int) ($result["study_hours"] ?? 1));
$difficulty = (string) ($result["difficulty"] ?? "Medium");
$summary = (string) ($result["summary"] ?? "No summary was returned.");
$studyPlan = (string) ($result["study_plan"] ?? "Review the PDF in focused sessions and test yourself after each pass.");

$stmt = $conn->prepare(
    "INSERT INTO ai_results (user_id, file_name, study_hours, difficulty, summary, study_plan)
     VALUES (?, ?, ?, ?, ?, ?)"
);

if (!$stmt) {
    render_upload_message("Database issue", "The analysis was completed, but it could not be saved.");
}

$stmt->bind_param("isisss", $user_id, $safeName, $studyHours, $difficulty, $summary, $studyPlan);

if (!$stmt->execute()) {
    render_upload_message("Database issue", "The analysis was completed, but it could not be saved.");
}

$_SESSION["flash_success"] = "Your PDF was analyzed and added to the dashboard.";
header("Location: dashboard.php");
exit;
?>
