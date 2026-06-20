<?php
session_start();
require_once __DIR__ . "/config.php";

/** @var mysqli $conn */

function render_auth_message($title, $message, $linkText, $linkHref)
{
    $safeTitle = htmlspecialchars($title, ENT_QUOTES, "UTF-8");
    $safeMessage = htmlspecialchars($message, ENT_QUOTES, "UTF-8");
    $safeLinkText = htmlspecialchars($linkText, ENT_QUOTES, "UTF-8");
    $safeLinkHref = htmlspecialchars($linkHref, ENT_QUOTES, "UTF-8");

    echo "<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{$safeTitle}</title>
    <link rel=\"stylesheet\" href=\"style.css\">
</head>
<body class=\"auth-page\">
    <main class=\"auth-card status-card\">
        <span class=\"eyebrow\">Study Planner</span>
        <h1>{$safeTitle}</h1>
        <p>{$safeMessage}</p>
        <a class=\"button-link\" href=\"{$safeLinkHref}\">{$safeLinkText}</a>
    </main>
</body>
</html>";
    exit;
}

if ($_SERVER["REQUEST_METHOD"] !== "POST") {
    header("Location: login.html");
    exit;
}

$email = trim($_POST["email"] ?? "");
$pass = (string) ($_POST["password"] ?? "");

if ($email === "" || $pass === "") {
    render_auth_message("Login failed", "Please enter both email and password.", "Back to Login", "login.html");
}

$stmt = $conn->prepare("SELECT id, password FROM users WHERE email = ? LIMIT 1");

if (!$stmt) {
    render_auth_message("Login failed", "The database could not prepare the login request.", "Try Again", "login.html");
}

$stmt->bind_param("s", $email);
$stmt->execute();
$result = $stmt->get_result();
$user = $result ? $result->fetch_assoc() : null;

if ($user && password_verify($pass, $user["password"])) {
    $_SESSION["user_id"] = (int) $user["id"];
    header("Location: dashboard.php");
    exit;
}

render_auth_message("Login failed", "The email or password is incorrect.", "Try Again", "login.html");
?>
