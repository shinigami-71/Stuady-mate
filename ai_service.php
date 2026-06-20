<?php
const AI_SERVICE_URL = "http://127.0.0.1:8000";

function ai_service_available($timeoutSeconds = 1, &$versionError = "")
{
    $ch = curl_init(AI_SERVICE_URL . "/openapi.json");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, $timeoutSeconds);
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeoutSeconds);

    $response = curl_exec($ch);
    $httpCode = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($response === false || $httpCode !== 200) {
        return false;
    }

    $health = json_decode($response, true);
    $endpoints = is_array($health) && isset($health["endpoints"]) && is_array($health["endpoints"])
        ? $health["endpoints"]
        : [];

    if (!in_array("/suggest", $endpoints, true)) {
        $versionError = "The AI backend is running an older version. Close the old Study Planner AI window, then open start_project.bat again.";
        return false;
    }

    return true;
}

function ai_start_service(&$error = "")
{
    $versionError = "";

    if (ai_service_available(1, $versionError)) {
        return true;
    }

    if ($versionError !== "") {
        $error = $versionError;
        return false;
    }

    $root = __DIR__;
    $venvPython = $root . DIRECTORY_SEPARATOR . ".venv" . DIRECTORY_SEPARATOR . "Scripts" . DIRECTORY_SEPARATOR . "python.exe";
    $fallbackPython = $root . DIRECTORY_SEPARATOR . "venv" . DIRECTORY_SEPARATOR . "Scripts" . DIRECTORY_SEPARATOR . "python.exe";
    $launcher = $root . DIRECTORY_SEPARATOR . "start_ai_backend.vbs";

    if (!file_exists($venvPython) && file_exists($fallbackPython)) {
        $venvPython = $fallbackPython;
    }

    if (!file_exists($venvPython)) {
        $error = "AI backend environment is missing. Run setup_ai_backend.bat once, then try again.";
        return false;
    }

    if (!file_exists($launcher)) {
        $error = "AI backend launcher is missing.";
        return false;
    }

    $command = "wscript.exe " . escapeshellarg($launcher);
    @pclose(@popen($command, "r"));

    $deadline = microtime(true) + 15;

    while (microtime(true) < $deadline) {
        usleep(500000);

        if (ai_service_available(1, $versionError)) {
            return true;
        }

        if ($versionError !== "") {
            $error = $versionError;
            return false;
        }
    }

    $logFile = $root . DIRECTORY_SEPARATOR . "ai_backend" . DIRECTORY_SEPARATOR . "server.log";
    $logText = "";

    if (file_exists($logFile)) {
        $logText = trim((string) file_get_contents($logFile));
    }

    $error = "AI backend could not start on 127.0.0.1:8000. Open start_project.bat or start_ai_backend.bat, then try again.";

    if ($logText !== "") {
        $error .= " Backend log: " . substr($logText, -800);
    }

    return false;
}

function ai_post($endpoint, $payload, $timeoutSeconds, &$error = "")
{
    if (!ai_start_service($error)) {
        return null;
    }

    $ch = curl_init(AI_SERVICE_URL . $endpoint);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 5);
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeoutSeconds);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ["Content-Type: application/json"]);

    $response = curl_exec($ch);

    if ($response === false) {
        $error = curl_error($ch);
        curl_close($ch);
        return null;
    }

    curl_close($ch);
    $result = json_decode($response, true);

    if (!is_array($result)) {
        $error = "The AI service returned an unreadable response.";
        return null;
    }

    if (isset($result["error"])) {
        $error = (string) $result["error"];
        return null;
    }

    return $result;
}
?>
