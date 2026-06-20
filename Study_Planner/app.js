(function () {
    var form = document.getElementById("reminder-form");
    var timeInput = document.getElementById("reminder-time");
    var typeInput = document.getElementById("reminder-type");
    var lengthInput = document.getElementById("reminder-length");
    var focusInput = document.getElementById("reminder-focus");
    var status = document.getElementById("reminder-status");
    var focusButton = document.getElementById("start-focus");
    var stopButton = document.getElementById("stop-focus");
    var resetButton = document.getElementById("reset-focus");
    var clearButton = document.getElementById("clear-reminder");
    var enableNotificationsButton = document.getElementById("enable-notifications");
    var testNotificationButton = document.getElementById("test-notification");
    var countdown = document.getElementById("focus-countdown");
    var sessionStatus = document.getElementById("focus-session-status");
    var notificationStatus = document.getElementById("notification-status");
    var reminderToast = document.getElementById("reminder-toast");
    var reminderTimer = null;
    var focusTimer = null;
    var focusStartedAt = null;
    var focusInitialSeconds = 0;
    var secondsLeft = 0;
    var storageKey = "studyPlanner.reminder.v3";
    var reviewKey = "studyPlanner.reviewedDocuments.v1";
    var progressKey = "studyPlanner.studyProgress.v1";
    var reminderTypes = {
        study: {
            label: "Study session",
            title: "Study session reminder",
            body: "Start your planned focus session."
        },
        pdf: {
            label: "PDF review",
            title: "PDF review reminder",
            body: "Review your PDF summary and ask two practice questions."
        },
        exam: {
            label: "Exam prep",
            title: "Exam prep reminder",
            body: "Revise the highest-priority topics and test yourself from memory."
        },
        break: {
            label: "Short break",
            title: "Break reminder",
            body: "Take a short break, then return with a clear focus goal."
        }
    };

    function readJson(key) {
        try {
            return JSON.parse(window.localStorage.getItem(key) || "{}");
        } catch (error) {
            return {};
        }
    }

    function writeJson(key, value) {
        window.localStorage.setItem(key, JSON.stringify(value));
    }

    function formatClock(date) {
        return date.toLocaleTimeString([], {
            hour: "numeric",
            minute: "2-digit"
        });
    }

    function formatDuration(totalSeconds) {
        var safeSeconds = Math.max(0, totalSeconds);
        var minutes = Math.floor(safeSeconds / 60);
        var seconds = safeSeconds % 60;
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }

    function formatStudyMinutes(totalMinutes) {
        var safeMinutes = Math.max(0, Math.round(Number(totalMinutes) || 0));
        var hours = Math.floor(safeMinutes / 60);
        var minutes = safeMinutes % 60;

        if (hours && minutes) {
            return hours + "h " + minutes + "m";
        }

        if (hours) {
            return hours + "h";
        }

        return minutes + "m";
    }

    function progressState() {
        var progress = readJson(progressKey);

        return {
            focusMinutes: Math.max(0, Math.round(Number(progress.focusMinutes) || 0))
        };
    }

    function writeProgress(progress) {
        writeJson(progressKey, {
            focusMinutes: Math.max(0, Math.round(Number(progress.focusMinutes) || 0))
        });
    }

    function documentStudyMinutes(card) {
        return Math.max(0, Math.round(Number(card.dataset.studyMinutes) || 0));
    }

    function reviewedStudyMinutes(reviewed) {
        var minutes = 0;

        document.querySelectorAll("[data-study-card]").forEach(function (card) {
            if (reviewed[card.dataset.studyCard]) {
                minutes += documentStudyMinutes(card);
            }
        });

        return minutes;
    }

    function updateStudyProgress() {
        var remainingElement = document.getElementById("remaining-study-time");

        if (!remainingElement) {
            return;
        }

        var reviewed = readJson(reviewKey);
        var progress = progressState();
        var totalMinutes = Math.max(0, Math.round(Number(remainingElement.dataset.totalMinutes) || 0));
        var reviewedMinutes = reviewedStudyMinutes(reviewed);
        var completedMinutes = Math.min(totalMinutes, reviewedMinutes + progress.focusMinutes);
        var remainingMinutes = Math.max(0, totalMinutes - completedMinutes);
        var todayTarget = document.getElementById("today-target-time");

        remainingElement.textContent = formatStudyMinutes(remainingMinutes);
        remainingElement.title = formatStudyMinutes(completedMinutes) + " completed";

        if (todayTarget) {
            todayTarget.textContent = formatStudyMinutes(Math.min(Math.max(0, Number(todayTarget.dataset.baseMinutes) || 0), remainingMinutes));
        }

        document.querySelectorAll("[data-document-remaining]").forEach(function (item) {
            var baseMinutes = Math.max(0, Math.round(Number(item.dataset.baseMinutes) || 0));
            var isReviewed = Boolean(reviewed[item.dataset.documentRemaining]);

            item.textContent = formatStudyMinutes(isReviewed ? 0 : baseMinutes) + " remaining";
        });
    }

    function activeFocusSeconds() {
        if (!focusStartedAt) {
            return Math.max(0, focusInitialSeconds - secondsLeft);
        }

        return Math.max(0, Math.round((Date.now() - focusStartedAt) / 1000));
    }

    function recordFocusProgress(elapsedSeconds) {
        if (elapsedSeconds < 60) {
            return 0;
        }

        var minutes = Math.max(1, Math.floor(elapsedSeconds / 60));
        var progress = progressState();
        progress.focusMinutes += minutes;
        writeProgress(progress);
        updateStudyProgress();
        return minutes;
    }

    function currentReminderState() {
        return {
            time: timeInput ? timeInput.value : "",
            type: typeInput ? typeInput.value || "study" : "study",
            length: lengthInput ? lengthInput.value || "50" : "50",
            focus: focusInput ? focusInput.value.trim() : ""
        };
    }

    function getNextReminder(timeValue) {
        var parts = timeValue.split(":");
        var target = new Date();
        target.setHours(Number(parts[0]), Number(parts[1]), 0, 0);

        if (target <= new Date()) {
            target.setDate(target.getDate() + 1);
        }

        return target;
    }

    function setSessionStatus(message) {
        if (sessionStatus) {
            sessionStatus.textContent = message;
        }
    }

    function reminderType(type) {
        return reminderTypes[type] || reminderTypes.study;
    }

    function reminderCopy(state) {
        var type = reminderType(state.type);

        return {
            title: type.title,
            body: state.focus || type.body
        };
    }

    function showInPageNotification(title, body) {
        if (!reminderToast) {
            return;
        }

        reminderToast.textContent = title + ": " + body;
        reminderToast.hidden = false;
        reminderToast.classList.add("is-visible");

        window.setTimeout(function () {
            reminderToast.classList.remove("is-visible");
            reminderToast.hidden = true;
        }, 7000);
    }

    function updateNotificationStatus() {
        if (!notificationStatus || !enableNotificationsButton) {
            return;
        }

        if (!("Notification" in window)) {
            notificationStatus.textContent = "Browser notifications are not available here.";
            enableNotificationsButton.disabled = true;
            return;
        }

        if (Notification.permission === "granted") {
            notificationStatus.textContent = "Browser notifications are enabled.";
            enableNotificationsButton.textContent = "Notifications Enabled";
            enableNotificationsButton.disabled = true;
            return;
        }

        enableNotificationsButton.disabled = false;
        enableNotificationsButton.textContent = "Enable Notifications";

        if (Notification.permission === "denied") {
            notificationStatus.textContent = "Browser notifications are blocked.";
            return;
        }

        notificationStatus.textContent = "Browser notifications are not enabled yet.";
    }

    function requestNotificationPermission() {
        if (!("Notification" in window)) {
            updateNotificationStatus();
            return Promise.resolve(false);
        }

        if (Notification.permission === "granted") {
            updateNotificationStatus();
            return Promise.resolve(true);
        }

        if (Notification.permission === "denied") {
            updateNotificationStatus();
            return Promise.resolve(false);
        }

        return Notification.requestPermission().then(function (permission) {
            updateNotificationStatus();
            return permission === "granted";
        });
    }

    function sendNotification(title, body) {
        if ("Notification" in window && Notification.permission === "granted") {
            new Notification(title, { body: body });
        }

        showInPageNotification(title, body);
    }

    function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, function (char) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                "\"": "&quot;",
                "'": "&#039;"
            }[char];
        });
    }

    function updateStatus(state) {
        if (!status) {
            return;
        }

        if (!state.time) {
            status.textContent = "Choose a time, session length, and focus goal.";
            return;
        }

        var nextReminder = getNextReminder(state.time);
        var type = reminderType(state.type);
        var focus = state.focus ? " | " + state.focus : "";
        status.textContent = "Next " + type.label.toLowerCase() + ": " + formatClock(nextReminder) + " | " + state.length + " min" + focus;
    }

    function scheduleReminder(state) {
        window.clearTimeout(reminderTimer);
        updateStatus(state);

        if (!state.time) {
            return;
        }

        reminderTimer = window.setTimeout(function () {
            var copy = reminderCopy(state);
            sendNotification(copy.title, copy.body);
            scheduleReminder(state);
        }, getNextReminder(state.time).getTime() - Date.now());
    }

    function setCountdown(totalSeconds) {
        if (countdown) {
            countdown.textContent = formatDuration(totalSeconds);
        }
    }

    function startFocusTimer(minutes) {
        secondsLeft = Math.max(1, Number(minutes || 50)) * 60;
        window.clearInterval(focusTimer);
        focusStartedAt = Date.now();
        focusInitialSeconds = secondsLeft;
        setCountdown(secondsLeft);
        setSessionStatus("Focus session running.");

        focusTimer = window.setInterval(function () {
            secondsLeft -= 1;
            setCountdown(secondsLeft);

            if (secondsLeft <= 0) {
                window.clearInterval(focusTimer);
                focusTimer = null;
                var countedMinutes = recordFocusProgress(focusInitialSeconds);
                focusStartedAt = null;
                focusInitialSeconds = 0;
                setSessionStatus("Session complete. " + countedMinutes + " min removed from remaining time.");
                sendNotification("Focus session complete", "Take a short break, then test yourself from memory.");
            }
        }, 1000);
    }

    function stopFocusTimer() {
        var countedMinutes = recordFocusProgress(activeFocusSeconds());
        window.clearInterval(focusTimer);
        focusTimer = null;
        focusStartedAt = null;
        focusInitialSeconds = 0;
        setCountdown(secondsLeft);
        setSessionStatus(countedMinutes ? countedMinutes + " min removed from remaining time." : "Timer stopped. Start again when you are ready.");
    }

    function resetFocusTimer() {
        var minutes = currentReminderState().length || "50";
        window.clearInterval(focusTimer);
        focusTimer = null;
        focusStartedAt = null;
        focusInitialSeconds = 0;
        secondsLeft = Math.max(1, Number(minutes)) * 60;
        setCountdown(secondsLeft);
        setSessionStatus("Timer reset.");
    }

    function copySummary(button) {
        var target = document.getElementById(button.dataset.summaryTarget || "");

        if (!target || !navigator.clipboard) {
            return;
        }

        navigator.clipboard.writeText(target.innerText.trim()).then(function () {
            button.textContent = "Copied";
            window.setTimeout(function () {
                button.textContent = "Copy Summary";
            }, 1400);
        });
    }

    function printSummary(button) {
        var target = document.getElementById(button.dataset.summaryTarget || "");

        if (!target) {
            return;
        }

        var printWindow = window.open("", "_blank", "width=760,height=900");

        if (!printWindow) {
            return;
        }

        var title = escapeHtml(button.dataset.title || "Study Summary");
        var body = escapeHtml(target.innerText.trim());

        printWindow.document.write(
            "<html><head><title>" + title + "</title>" +
            "<style>body{font-family:Arial,sans-serif;line-height:1.6;padding:32px;color:#18222f;}h1{font-size:24px;}pre{white-space:pre-wrap;font-family:inherit;}</style>" +
            "</head><body><h1>" + title + "</h1><pre>" + body + "</pre></body></html>"
        );
        printWindow.document.close();
        printWindow.focus();
        printWindow.print();
    }

    function updateReviewBadges() {
        var reviewed = readJson(reviewKey);

        document.querySelectorAll("[data-review-badge]").forEach(function (badge) {
            var id = badge.dataset.reviewBadge;

            if (reviewed[id]) {
                badge.textContent = "Reviewed";
                badge.classList.add("is-reviewed");
            } else {
                badge.textContent = "Not reviewed";
                badge.classList.remove("is-reviewed");
            }
        });

        document.querySelectorAll(".mark-reviewed").forEach(function (button) {
            button.textContent = reviewed[button.dataset.reviewId] ? "Reviewed" : "Mark Reviewed";
        });

        updateStudyProgress();
    }

    if (form && timeInput && status) {
        var savedState = readJson(storageKey);

        if (savedState.time) {
            timeInput.value = savedState.time;
            if (typeInput) {
                typeInput.value = savedState.type || "study";
            }
            lengthInput.value = savedState.length || "50";
            focusInput.value = savedState.focus || "";
            scheduleReminder(savedState);
            secondsLeft = Number(savedState.length || 50) * 60;
            setCountdown(secondsLeft);
        } else {
            updateStatus({});
            resetFocusTimer();
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var state = currentReminderState();
            writeJson(storageKey, state);
            scheduleReminder(state);
            resetFocusTimer();
            setSessionStatus("Reminder saved.");

            requestNotificationPermission().then(function (enabled) {
                setSessionStatus(enabled ? "Reminder saved. Browser notifications enabled." : "Reminder saved. On-page alerts are ready.");
            });
        });

        if (enableNotificationsButton) {
            enableNotificationsButton.addEventListener("click", function () {
                requestNotificationPermission().then(function (enabled) {
                    setSessionStatus(enabled ? "Browser notifications enabled." : "Browser notifications are not enabled.");
                });
            });
        }

        if (testNotificationButton) {
            testNotificationButton.addEventListener("click", function () {
                requestNotificationPermission().then(function () {
                    var copy = reminderCopy(currentReminderState());
                    sendNotification(copy.title, copy.body);
                    setSessionStatus("Test notification sent.");
                });
            });
        }

        document.querySelectorAll("[data-preset-minutes]").forEach(function (button) {
            button.addEventListener("click", function () {
                lengthInput.value = button.dataset.presetMinutes;
                resetFocusTimer();
            });
        });

        if (focusButton) {
            focusButton.addEventListener("click", function () {
                startFocusTimer(currentReminderState().length);
            });
        }

        if (stopButton) {
            stopButton.addEventListener("click", stopFocusTimer);
        }

        if (resetButton) {
            resetButton.addEventListener("click", resetFocusTimer);
        }

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                window.localStorage.removeItem(storageKey);
                timeInput.value = "";
                if (typeInput) {
                    typeInput.value = "study";
                }
                focusInput.value = "";
                lengthInput.value = "50";
                window.clearTimeout(reminderTimer);
                resetFocusTimer();
                updateStatus({});
                setSessionStatus("Saved reminder cleared.");
            });
        }
    }

    updateNotificationStatus();
    document.querySelectorAll(".copy-summary").forEach(function (button) {
        button.addEventListener("click", function () {
            copySummary(button);
        });
    });

    document.querySelectorAll(".print-summary").forEach(function (button) {
        button.addEventListener("click", function () {
            printSummary(button);
        });
    });

    document.querySelectorAll(".mark-reviewed").forEach(function (button) {
        button.addEventListener("click", function () {
            var reviewed = readJson(reviewKey);
            var id = button.dataset.reviewId;
            reviewed[id] = !reviewed[id];
            writeJson(reviewKey, reviewed);
            updateReviewBadges();
            button.textContent = reviewed[id] ? "Reviewed" : "Mark Reviewed";
        });
    });

    updateReviewBadges();
}());
