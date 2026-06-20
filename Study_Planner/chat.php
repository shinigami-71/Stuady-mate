<?php
session_start();
include "config.php";
include "ai_service.php";

if (!isset($_SESSION["user_id"])) {
    header("Location: login.html");
    exit;
}

function h($value)
{
    return htmlspecialchars((string) $value, ENT_QUOTES, "UTF-8");
}

function display_file_name($fileName)
{
    $name = preg_replace("/^user\d+_\d{8}_\d{6}_[a-f0-9]{6}_/", "", (string) $fileName);
    return $name ?: (string) $fileName;
}

function format_text($value)
{
    return nl2br(h($value));
}

$userId = (int) $_SESSION["user_id"];
$stmt = $conn->prepare("SELECT file_name FROM ai_results WHERE user_id = ?");
$stmt->bind_param("i", $userId);
$stmt->execute();
$filesRes = $stmt->get_result();
$files = [];

while ($row = $filesRes->fetch_assoc()) {
    $files[] = $row["file_name"];
}

$selectedFile = $_POST["file"] ?? ($_GET["file"] ?? ($files[0] ?? ""));
$question = trim($_POST["q"] ?? "");
$answer = "";
$error = "";
$suggestions = [];
$suggestionError = "";

if ($_SERVER["REQUEST_METHOD"] === "POST") {
    if ($selectedFile === "" || !in_array($selectedFile, $files, true)) {
        $error = "Please choose one of your uploaded PDFs.";
    } elseif ($question === "") {
        $error = "Please enter a question.";
    } else {
        $res = ai_post("/ask", [
            "file_path" => $selectedFile,
            "question" => $question,
        ], 90, $error);

        if ($res !== null) {
            $answer = (string) ($res["answer"] ?? "No answer was returned.");
        }
    }
}

if ($selectedFile !== "" && in_array($selectedFile, $files, true)) {
    $suggestRes = ai_post("/suggest", [
        "file_path" => $selectedFile,
    ], 60, $suggestionError);

    if (is_array($suggestRes) && isset($suggestRes["questions"]) && is_array($suggestRes["questions"])) {
        $suggestions = $suggestRes["questions"];
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chat - Study Planner</title>
    <link rel="stylesheet" href="style.css">
</head>
<body class="app-page">
    <header class="topbar">
        <a class="brand" href="dashboard.php" aria-label="Study Planner dashboard">
            <span class="brand-mark">SP</span>
            <span>
                <strong>Study Planner</strong>
                <small>AI PDF workspace</small>
            </span>
        </a>
        <nav class="topnav" aria-label="Main navigation">
            <a href="index.html">Home</a>
            <a href="dashboard.php">Dashboard</a>
            <a href="upload.html">Upload</a>
            <a href="logout.php">Logout</a>
        </nav>
    </header>

    <main class="page-shell narrow-shell">
        <section class="page-intro">
            <span class="eyebrow">AI chat</span>
            <h1>Ask focused questions from your uploaded PDFs.</h1>
            <p>The answer is pulled from the selected document and includes source pages when the PDF text supports it.</p>
        </section>

        <?php if ($error): ?>
            <div class="notice notice-error"><?php echo h($error); ?></div>
        <?php endif; ?>

        <?php if (empty($files)): ?>
            <article class="empty-state">
                <span class="empty-icon">PDF</span>
                <h3>No PDFs available</h3>
                <p>Upload a PDF first, then come back to ask questions about it.</p>
                <a class="button-link" href="upload.html">Upload PDF</a>
            </article>
        <?php else: ?>
            <form class="panel-form chat-panel" action="chat.php" method="POST">
                <label for="file">Study PDF</label>
                <select id="file" name="file" required>
                    <?php foreach ($files as $file): ?>
                        <option value="<?php echo h($file); ?>" <?php echo $selectedFile === $file ? "selected" : ""; ?>>
                            <?php echo h(display_file_name($file)); ?>
                        </option>
                    <?php endforeach; ?>
                </select>

                <label for="q">Question</label>
                <textarea id="q" name="q" rows="5" placeholder="Example: Explain the most important concept in simple words." required><?php echo h($question); ?></textarea>

                <button type="submit">Ask AI</button>
            </form>

            <?php if (!empty($suggestions)): ?>
                <section class="suggestion-panel">
                    <div class="section-heading">
                        <div>
                            <span class="eyebrow">From this PDF</span>
                            <h2>Suggested questions</h2>
                        </div>
                        <span class="hint-chip">One click study prompts</span>
                    </div>
                    <div class="suggestion-grid">
                        <?php foreach ($suggestions as $item): ?>
                            <?php
                                $prompt = is_array($item) ? (string) ($item["question"] ?? "") : (string) $item;
                                $type = is_array($item) ? (string) ($item["type"] ?? "Prompt") : "Prompt";
                            ?>
                            <?php if ($prompt !== ""): ?>
                                <form class="suggestion-form" action="chat.php" method="POST">
                                    <input type="hidden" name="file" value="<?php echo h($selectedFile); ?>">
                                    <input type="hidden" name="q" value="<?php echo h($prompt); ?>">
                                    <button type="submit">
                                        <span><?php echo h($type); ?></span>
                                        <strong><?php echo h($prompt); ?></strong>
                                    </button>
                                </form>
                            <?php endif; ?>
                        <?php endforeach; ?>
                    </div>
                </section>
            <?php elseif ($suggestionError): ?>
                <div class="notice">Suggested questions will appear after the AI service is running.</div>
            <?php endif; ?>
        <?php endif; ?>

        <?php if ($answer): ?>
            <article class="answer-card">
                <span class="eyebrow">Answer</span>
                <div><?php echo format_text($answer); ?></div>
            </article>
        <?php endif; ?>
    </main>

    <script>
        var fileSelect = document.getElementById("file");

        if (fileSelect) {
            fileSelect.addEventListener("change", function () {
                window.location.href = "chat.php?file=" + encodeURIComponent(fileSelect.value);
            });
        }
    </script>
</body>
</html>
