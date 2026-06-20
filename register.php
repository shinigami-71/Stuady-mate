<?php
include "config.php";

function render_register_message($title, $message, $linkText, $linkHref)
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
    header("Location: register.html");
    exit;
}

$email = trim($_POST["email"] ?? "");
$password = (string) ($_POST["password"] ?? "");

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    render_register_message("Registration failed", "Please enter a valid email address.", "Back to Register", "register.html");
}

if (strlen($password) < 6) {
    render_register_message("Registration failed", "Password must be at least 6 characters.", "Back to Register", "register.html");
}

$check = $conn->prepare("SELECT id FROM users WHERE email = ? LIMIT 1");
$check->bind_param("s", $email);
$check->execute();

if ($check->get_result()->fetch_assoc()) {
    render_register_message("Account already exists", "An account with this email is already registered.", "Go to Login", "login.html");
}

$hashedPassword = password_hash($password, PASSWORD_DEFAULT);
$stmt = $conn->prepare("INSERT INTO users (email, password) VALUES (?, ?)");
$stmt->bind_param("ss", $email, $hashedPassword);

if (!$stmt->execute()) {
    render_register_message("Registration failed", "The account could not be created right now.", "Try Again", "register.html");
}

render_register_message("Account created", "Your account is ready. You can sign in now.", "Go to Login", "login.html");
?>
