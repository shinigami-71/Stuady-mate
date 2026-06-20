<?php
session_start();
include "config.php";

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

function difficulty_class($difficulty)
{
    $value = strtolower((string) $difficulty);
    return in_array($value, ["easy", "medium", "hard"], true) ? $value : "medium";
}

$userId = (int) $_SESSION["user_id"];
$stmt = $conn->prepare("SELECT file_name, study_hours, difficulty, summary, study_plan FROM ai_results WHERE user_id = ?");
$stmt->bind_param("i", $userId);
$stmt->execute();
$res = $stmt->get_result();

$results = [];

while ($row = $res->fetch_assoc()) {
    $results[] = $row;
}

$totalFiles = count($results);
$totalHours = array_sum(array_map(fn($row) => (int) $row["study_hours"], $results));
$totalMinutes = $totalHours * 60;
$hardCount = count(array_filter($results, fn($row) => strtolower((string) $row["difficulty"]) === "hard"));
$mediumCount = count(array_filter($results, fn($row) => strtolower((string) $row["difficulty"]) === "medium"));
$todayMinutes = $totalFiles > 0 ? min(110, max(35, (int) ceil(($totalHours * 60) / max(1, $totalFiles * 2)))) : 0;
$priority = null;

foreach ($results as $row) {
    if ($priority === null || (int) $row["study_hours"] > (int) $priority["study_hours"]) {
        $priority = $row;
    }
}

$scheduleItems = array_slice($results, 0, 4);
$flashSuccess = $_SESSION["flash_success"] ?? "";
unset($_SESSION["flash_success"]);
$dashboardPrompts = [
    ["label" => "Objectives", "question" => "What are the main objectives and why are they important?"],
    ["label" => "Results", "question" => "What are the key results and observations?"],
    ["label" => "Quiz", "question" => "Make a short quiz from this PDF."],
    ["label" => "Revise first", "question" => "What should I revise first for an exam, lab viva, or class test?"],
];
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Study Planner</title>
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
            <a href="upload.html">Upload</a>
            <a href="chat.php">AI Chat</a>
            <a href="logout.php">Logout</a>
        </nav>
    </header>

    <main class="page-shell">
        <?php if ($flashSuccess): ?>
            <div class="notice notice-success"><?php echo h($flashSuccess); ?></div>
        <?php endif; ?>

        <section class="workspace-hero">
            <div class="workspace-copy">
                <span class="eyebrow">Command center</span>
                <h1>Plan the next study session from your PDF library.</h1>
                <p>Review summaries, ask document questions, follow the suggested session rhythm, and keep the reminder console ready.</p>
                <div class="hero-actions">
                    <a class="button-link" href="upload.html">Upload PDF</a>
                    <a class="button-link button-link-secondary" href="chat.php">Ask AI</a>
                </div>
            </div>

            <aside class="reminder-console" aria-labelledby="reminder-title">
                <div class="panel-heading">
                    <span class="eyebrow">Reminder</span>
                    <h2 id="reminder-title">Daily focus console</h2>
                </div>
                <p id="reminder-status" class="reminder-status">No reminder saved yet.</p>
                <form id="reminder-form" class="reminder-form">
                    <label for="reminder-time">Study time</label>
                    <input id="reminder-time" name="reminder-time" type="time" required>

                    <label for="reminder-type">Reminder type</label>
                    <select id="reminder-type" name="reminder-type">
                        <option value="study" selected>Study session</option>
                        <option value="pdf">PDF review</option>
                        <option value="exam">Exam prep</option>
                        <option value="break">Short break</option>
                    </select>

                    <label for="reminder-length">Session length</label>
                    <select id="reminder-length" name="reminder-length">
                        <option value="25">25 minutes</option>
                        <option value="35">35 minutes</option>
                        <option value="50" selected>50 minutes</option>
                        <option value="75">75 minutes</option>
                        <option value="90">90 minutes</option>
                    </select>
                    <div class="preset-row" aria-label="Session length presets">
                        <button type="button" data-preset-minutes="25">25m</button>
                        <button type="button" data-preset-minutes="50">50m</button>
                        <button type="button" data-preset-minutes="75">75m</button>
                    </div>

                    <label for="reminder-focus">Focus goal</label>
                    <input id="reminder-focus" name="reminder-focus" placeholder="Example: revise objectives and results">

                    <div class="reminder-actions">
                        <button type="submit">Save Reminder</button>
                        <button id="start-focus" type="button" class="button-muted">Start Focus</button>
                        <button id="stop-focus" type="button" class="button-muted">Stop</button>
                        <button id="reset-focus" type="button" class="button-muted">Reset</button>
                    </div>
                    <div class="notification-actions">
                        <button id="enable-notifications" type="button" class="button-muted">Enable Notifications</button>
                        <button id="test-notification" type="button" class="button-muted">Test Notification</button>
                    </div>
                    <button id="clear-reminder" type="button" class="text-button">Clear saved reminder</button>
                </form>
                <div class="timer-display" aria-live="polite">
                    <span>Focus timer</span>
                    <strong id="focus-countdown">00:00</strong>
                </div>
                <p id="focus-session-status" class="session-status">Ready for a focused session.</p>
                <p id="notification-status" class="notification-status">Notifications not checked yet.</p>
                <div id="reminder-toast" class="reminder-toast" role="status" aria-live="polite" hidden></div>
            </aside>
        </section>

        <section class="metric-strip" aria-label="Study overview">
            <article>
                <span>PDFs</span>
                <strong><?php echo h($totalFiles); ?></strong>
            </article>
            <article>
                <span>Remaining time</span>
                <strong id="remaining-study-time" data-total-minutes="<?php echo h($totalMinutes); ?>"><?php echo h($totalHours . "h"); ?></strong>
            </article>
            <article>
                <span>Medium files</span>
                <strong><?php echo h($mediumCount); ?></strong>
            </article>
            <article>
                <span>Hard files</span>
                <strong><?php echo h($hardCount); ?></strong>
            </article>
            <article>
                <span>Today target</span>
                <strong id="today-target-time" data-base-minutes="<?php echo h($todayMinutes); ?>"><?php echo $todayMinutes ? h($todayMinutes . "m") : "0m"; ?></strong>
            </article>
        </section>

        <section class="dashboard-layout">
            <div class="dashboard-main">
                <section class="panel">
                    <div class="section-heading">
                        <div>
                            <span class="eyebrow">Today</span>
                            <h2>Suggested focus plan</h2>
                        </div>
                    </div>

                    <?php if ($totalFiles === 0): ?>
                        <div class="empty-state compact-empty">
                            <span class="empty-icon">PDF</span>
                            <h3>No files yet</h3>
                            <p>Upload a study PDF to generate your first plan.</p>
                            <a class="button-link" href="upload.html">Upload PDF</a>
                        </div>
                    <?php else: ?>
                        <div class="timeline">
                            <?php foreach ($scheduleItems as $index => $row): ?>
                                <article class="timeline-item">
                                    <span><?php echo h(str_pad((string) ($index + 1), 2, "0", STR_PAD_LEFT)); ?></span>
                                    <div>
                                        <h3><?php echo h(display_file_name($row["file_name"])); ?></h3>
                                        <p><?php echo h(min(90, max(35, (int) $row["study_hours"] * 30))); ?> minutes: read summary, ask two questions, then recall without notes.</p>
                                    </div>
                                </article>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </section>

                <section class="content-section">
                    <div class="section-heading">
                        <div>
                            <span class="eyebrow">Library</span>
                            <h2>Analyzed PDFs</h2>
                        </div>
                        <a class="text-link" href="upload.html">Add PDF</a>
                    </div>

                    <?php if ($totalFiles === 0): ?>
                        <article class="empty-state">
                            <span class="empty-icon">PDF</span>
                            <h3>Your library is empty</h3>
                            <p>Upload a PDF to create a summary, chat source, study plan, and reminder target.</p>
                        </article>
                    <?php else: ?>
                        <div class="document-grid">
                            <?php foreach ($results as $row): ?>
                                <?php
                                $documentId = md5($row["file_name"]);
                                $difficulty = difficulty_class($row["difficulty"]);
                                $studyMinutes = (int) $row["study_hours"] * 60;
                                $sessionMinutes = max(35, min(90, (int) ceil(((int) $row["study_hours"] * 60) / 2)));
                                ?>
                                <article class="document-card" data-study-card="<?php echo h($documentId); ?>" data-study-minutes="<?php echo h($studyMinutes); ?>">
                                    <div class="review-badge" data-review-badge="<?php echo h($documentId); ?>">Not reviewed</div>
                                    <div class="document-header">
                                        <div>
                                            <span class="doc-type">PDF</span>
                                            <h3><?php echo h(display_file_name($row["file_name"])); ?></h3>
                                        </div>
                                        <span class="difficulty-pill difficulty-<?php echo h($difficulty); ?>">
                                            <?php echo h($row["difficulty"]); ?>
                                        </span>
                                    </div>

                                    <div class="document-meta">
                                        <span data-document-remaining="<?php echo h($documentId); ?>" data-base-minutes="<?php echo h($studyMinutes); ?>"><?php echo h($row["study_hours"]); ?>h remaining</span>
                                        <span><?php echo h($sessionMinutes); ?> min sessions</span>
                                    </div>

                                    <div class="summary-block">
                                        <div id="summary-<?php echo h($documentId); ?>">
                                            <?php echo format_text($row["summary"]); ?>
                                        </div>
                                    </div>

                                    <details class="study-plan">
                                        <summary>Study plan</summary>
                                        <p><?php echo format_text($row["study_plan"]); ?></p>
                                    </details>

                                    <div class="question-chip-row" aria-label="Quick AI questions">
                                        <?php foreach ($dashboardPrompts as $prompt): ?>
                                            <form action="chat.php" method="POST">
                                                <input type="hidden" name="file" value="<?php echo h($row["file_name"]); ?>">
                                                <input type="hidden" name="q" value="<?php echo h($prompt["question"]); ?>">
                                                <button type="submit" class="question-chip"><?php echo h($prompt["label"]); ?></button>
                                            </form>
                                        <?php endforeach; ?>
                                    </div>

                                    <div class="card-actions">
                                        <button type="button" class="button-muted copy-summary" data-summary-target="summary-<?php echo h($documentId); ?>">Copy Summary</button>
                                        <button type="button" class="button-muted print-summary" data-summary-target="summary-<?php echo h($documentId); ?>" data-title="<?php echo h(display_file_name($row["file_name"])); ?>">Print Summary</button>
                                        <button type="button" class="button-muted mark-reviewed" data-review-id="<?php echo h($documentId); ?>">Mark Reviewed</button>
                                        <form action="reanalyze.php" method="POST">
                                            <input type="hidden" name="file" value="<?php echo h($row["file_name"]); ?>">
                                            <button type="submit" class="button-muted">Refresh Summary</button>
                                        </form>
                                    </div>

                                    <form class="quick-chat" action="chat.php" method="POST">
                                        <input type="hidden" name="file" value="<?php echo h($row["file_name"]); ?>">
                                        <label for="question-<?php echo h($documentId); ?>">Ask this PDF</label>
                                        <div>
                                            <input id="question-<?php echo h($documentId); ?>" name="q" placeholder="Ask about objectives, results, or conclusion" required>
                                            <button type="submit">Ask</button>
                                        </div>
                                    </form>
                                </article>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </section>
            </div>

            <aside class="dashboard-side">
                <section class="panel priority-panel">
                    <span class="eyebrow">Priority</span>
                    <?php if ($priority): ?>
                        <h2><?php echo h(display_file_name($priority["file_name"])); ?></h2>
                        <p><?php echo h($priority["study_hours"]); ?> hours estimated. Start with summary, then ask the AI for objectives and weak points.</p>
                        <a class="button-link button-link-secondary" href="chat.php?file=<?php echo h(urlencode($priority["file_name"])); ?>">Open Chat</a>
                        <div class="priority-prompts">
                            <?php foreach (array_slice($dashboardPrompts, 0, 3) as $prompt): ?>
                                <form action="chat.php" method="POST">
                                    <input type="hidden" name="file" value="<?php echo h($priority["file_name"]); ?>">
                                    <input type="hidden" name="q" value="<?php echo h($prompt["question"]); ?>">
                                    <button type="submit" class="text-button"><?php echo h($prompt["label"]); ?></button>
                                </form>
                            <?php endforeach; ?>
                        </div>
                    <?php else: ?>
                        <h2>No priority yet</h2>
                        <p>Your highest-effort PDF will appear here after upload.</p>
                    <?php endif; ?>
                </section>

                <section class="panel rhythm-panel">
                    <span class="eyebrow">Rhythm</span>
                    <h2>Recommended cycle</h2>
                    <div class="rhythm-list">
                        <span>Read summary</span>
                        <span>Ask AI</span>
                        <span>Recall</span>
                        <span>Revise</span>
                    </div>
                </section>

                <section class="panel rhythm-panel">
                    <span class="eyebrow">Tools</span>
                    <h2>Quick actions</h2>
                    <div class="rhythm-list">
                        <span>Refresh older summaries</span>
                        <span>Copy key points before class</span>
                        <span>Print summaries for revision</span>
                        <span>Mark files after recall practice</span>
                    </div>
                </section>
            </aside>
        </section>
    </main>

    <script src="app.js?v=20260620-progress"></script>
</body>
</html>
