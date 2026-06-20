<?php
$conn = new mysqli("localhost", "root", "", "study_planner");

if ($conn->connect_error) {
    http_response_code(500);
    die("Database connection failed.");
}

$conn->set_charset("utf8mb4");
?>
