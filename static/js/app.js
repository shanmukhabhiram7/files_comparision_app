/* File, Folder & ZIP Compare — front-end behaviour.
 *
 * This reproduces the interactivity Streamlit provided for free:
 *  - switching the comparison type swaps the visible inputs and keeps the
 *    previous result on screen,
 *  - toggling "Show spaces" or the custom labels re-renders the stored result
 *    without running the comparison again,
 *  - validation messages, the spinner and error boxes behave as before.
 */

(function () {
    "use strict";

    var CONFIG = window.APP_CONFIG || {};

    var form = document.getElementById("compare-form");
    var statusArea = document.getElementById("status-area");
    var resultsArea = document.getElementById("results-area");
    var customLabelRow = document.getElementById("custom-label-row");
    var useCustomLabels = document.getElementById("use-custom-labels");
    var customLeftLabel = document.getElementById("custom-left-label");
    var customRightLabel = document.getElementById("custom-right-label");
    var semanticJson = document.getElementById("semantic-json");
    var showSpaces = document.getElementById("show-spaces");

    var hasResult = false;
    var busy = false;
    var renderTimer = null;

    /* ------------------------------------------------------------------ */
    /* Helpers                                                             */
    /* ------------------------------------------------------------------ */

    function currentMode() {
        var checked = form.querySelector('input[name="mode"]:checked');
        return checked ? checked.value : "ZIP vs ZIP";
    }

    function labels() {
        if (!useCustomLabels.checked) {
            if (currentMode() === "Text vs Text") {
                return { left: "Source", right: "Target" };
            }
            return { left: "Left", right: "Right" };
        }
        return {
            left: (customLeftLabel.value || "").trim() || "Left",
            right: (customRightLabel.value || "").trim() || "Right"
        };
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatSize(bytes) {
        if (bytes < 1024) {
            return bytes + "B";
        }
        var units = ["KB", "MB", "GB", "TB"];
        var value = bytes / 1024;
        var index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value = value / 1024;
            index += 1;
        }
        return value.toFixed(1) + units[index];
    }

    function clearStatus() {
        statusArea.innerHTML = "";
    }

    function showAlert(kind, message) {
        var icons = {
            success: "✅",
            info: "ℹ️",
            warning: "⚠️",
            error: "🚨"
        };
        statusArea.innerHTML =
            '<div class="st-alert ' + kind + '">' +
            '<span class="st-alert-icon">' + icons[kind] + "</span>" +
            '<div class="st-alert-body">' + escapeHtml(message) + "</div>" +
            "</div>";
    }

    function showException(message, trace) {
        statusArea.innerHTML =
            '<div class="st-alert exception">' +
            '<div class="exception-title">' + escapeHtml(message) + "</div>" +
            "<pre>" + escapeHtml(trace || "") + "</pre>" +
            "</div>";
    }

    function showSpinner(message) {
        statusArea.innerHTML =
            '<div class="st-spinner">' +
            '<div class="spinner-ring"></div>' +
            "<span>" + escapeHtml(message) + "</span>" +
            "</div>";
    }

    /* ------------------------------------------------------------------ */
    /* Dynamic widget labels                                               */
    /* ------------------------------------------------------------------ */

    function applyLabels() {
        var current = labels();
        var nodes = form.querySelectorAll("[data-label-tpl]");
        Array.prototype.forEach.call(nodes, function (node) {
            var template = node.getAttribute("data-label-tpl");
            var side = node.getAttribute("data-side");
            node.textContent = template.replace(
                "{label}",
                side === "right" ? current.right : current.left
            );
        });
    }

    /* ------------------------------------------------------------------ */
    /* Mode panels                                                         */
    /* ------------------------------------------------------------------ */

    function applyMode() {
        var mode = currentMode();
        var panels = form.querySelectorAll(".mode-panel");
        Array.prototype.forEach.call(panels, function (panel) {
            panel.classList.toggle(
                "hidden",
                panel.getAttribute("data-mode") !== mode
            );
        });
        applyLabels();
        clearStatus();
    }

    /* ------------------------------------------------------------------ */
    /* File uploaders                                                      */
    /* ------------------------------------------------------------------ */

    var selectedFiles = {};

    function acceptsFile(uploader, file) {
        var accept = uploader.getAttribute("data-accept");
        if (!accept) {
            return true;
        }
        var name = (file.name || "").toLowerCase();
        return accept
            .split(",")
            .map(function (part) { return part.trim().toLowerCase(); })
            .filter(Boolean)
            .some(function (ext) { return name.endsWith(ext); });
    }

    function renderSelection(uploader) {
        var field = uploader.getAttribute("data-field");
        var container = uploader.querySelector(".st-uploader-selected");
        var file = selectedFiles[field];

        if (!file) {
            container.innerHTML = "";
            return;
        }

        container.innerHTML =
            '<div class="st-uploaded-file">' +
            '<span class="file-icon">' +
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>' +
            '<polyline points="14 2 14 8 20 8"></polyline></svg>' +
            "</span>" +
            '<span class="file-name" title="' + escapeHtml(file.name) + '">' +
            escapeHtml(file.name) + "</span>" +
            '<span class="file-size">' + formatSize(file.size) + "</span>" +
            '<button type="button" class="file-remove" aria-label="Remove file">' +
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
            '<line x1="18" y1="6" x2="6" y2="18"></line>' +
            '<line x1="6" y1="6" x2="18" y2="18"></line></svg>' +
            "</button>" +
            "</div>";

        container
            .querySelector(".file-remove")
            .addEventListener("click", function () {
                delete selectedFiles[field];
                uploader.querySelector(".st-uploader-input").value = "";
                renderSelection(uploader);
            });
    }

    function acceptFile(uploader, file) {
        var field = uploader.getAttribute("data-field");
        if (!file) {
            return;
        }
        if (!acceptsFile(uploader, file)) {
            showAlert("error", file.name + " is not an accepted file type. Only ZIP files are allowed.");
            return;
        }
        if (file.size > CONFIG.maxUploadMb * 1024 * 1024) {
            showAlert(
                "error",
                file.name + " is larger than the " + CONFIG.maxUploadMb + "MB per-file limit."
            );
            return;
        }
        clearStatus();
        selectedFiles[field] = file;
        renderSelection(uploader);
    }

    function initUploader(uploader) {
        var input = uploader.querySelector(".st-uploader-input");
        var dropzone = uploader.querySelector(".st-uploader-dropzone");
        var browse = uploader.querySelector(".browse-button");

        browse.addEventListener("click", function () {
            input.click();
        });

        input.addEventListener("change", function () {
            acceptFile(uploader, input.files && input.files[0]);
        });

        ["dragenter", "dragover"].forEach(function (name) {
            dropzone.addEventListener(name, function (event) {
                event.preventDefault();
                event.stopPropagation();
                dropzone.classList.add("dragover");
            });
        });

        ["dragleave", "drop"].forEach(function (name) {
            dropzone.addEventListener(name, function (event) {
                event.preventDefault();
                event.stopPropagation();
                dropzone.classList.remove("dragover");
            });
        });

        dropzone.addEventListener("drop", function (event) {
            var files = event.dataTransfer && event.dataTransfer.files;
            if (files && files.length) {
                acceptFile(uploader, files[0]);
            }
        });
    }

    /* ------------------------------------------------------------------ */
    /* Sortable result tables                                              */
    /* ------------------------------------------------------------------ */

    function initSortableTables(root) {
        var tables = root.querySelectorAll('.st-dataframe[data-sortable="1"]');
        Array.prototype.forEach.call(tables, function (wrapper) {
            var headers = wrapper.querySelectorAll("thead th");
            Array.prototype.forEach.call(headers, function (header, index) {
                header.addEventListener("click", function () {
                    var ascending = header.getAttribute("data-order") !== "asc";
                    Array.prototype.forEach.call(headers, function (other) {
                        other.removeAttribute("data-order");
                        other.classList.remove("sorted");
                        var arrow = other.querySelector(".sort-arrow");
                        if (arrow) {
                            arrow.textContent = "▲";
                        }
                    });
                    header.setAttribute("data-order", ascending ? "asc" : "desc");
                    header.classList.add("sorted");
                    var arrow = header.querySelector(".sort-arrow");
                    if (arrow) {
                        arrow.textContent = ascending ? "▲" : "▼";
                    }

                    var body = wrapper.querySelector("tbody");
                    var rows = Array.prototype.slice.call(body.querySelectorAll("tr"));
                    rows.sort(function (a, b) {
                        var left = a.children[index].textContent;
                        var right = b.children[index].textContent;
                        var comparison = left < right ? -1 : left > right ? 1 : 0;
                        return ascending ? comparison : -comparison;
                    });
                    rows.forEach(function (row) {
                        body.appendChild(row);
                    });
                });
            });
        });
    }

    function setResultsHtml(html) {
        resultsArea.innerHTML = html;
        initSortableTables(resultsArea);
        initResultActions(resultsArea);
    }

    /* ------------------------------------------------------------------ */
    /* Server calls                                                        */
    /* ------------------------------------------------------------------ */

    function displayOptionsPayload() {
        var current = labels();
        var data = new FormData();
        data.append("show_spaces", showSpaces.checked ? "true" : "false");
        data.append("use_custom_labels", useCustomLabels.checked ? "true" : "false");
        data.append("custom_left_label", customLeftLabel.value);
        data.append("custom_right_label", customRightLabel.value);
        data.append("mode", currentMode());
        // Sent for completeness; the server resolves labels the same way.
        data.append("left_label", current.left);
        data.append("right_label", current.right);
        return data;
    }

    function copyText(value) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(value);
        }
        return new Promise(function (resolve, reject) {
            var helper = document.createElement("textarea");
            helper.value = value;
            helper.style.position = "fixed";
            helper.style.opacity = "0";
            document.body.appendChild(helper);
            helper.select();
            try {
                document.execCommand("copy") ? resolve() : reject(new Error("Copy failed"));
            } catch (error) {
                reject(error);
            } finally {
                document.body.removeChild(helper);
            }
        });
    }

    function initResultActions(root) {
        var shareButton = root.querySelector('[data-action="share-result"]');
        var downloadButton = root.querySelector('[data-action="download-pdf"]');
        var copyButton = root.querySelector('[data-action="copy-share-link"]');

        if (shareButton) {
            shareButton.addEventListener("click", function () {
                if (busy) return;
                busy = true;
                shareButton.disabled = true;
                var originalText = shareButton.textContent;
                shareButton.textContent = "Creating link...";
                fetch(CONFIG.shareUrl, { method: "POST", body: displayOptionsPayload() })
                    .then(function (response) { return response.json(); })
                    .then(function (payload) {
                        if (payload.status !== "ok") {
                            throw new Error(payload.message || "Could not create the share link.");
                        }
                        var panel = root.querySelector("[data-share-panel]");
                        var input = root.querySelector("[data-share-link]");
                        if (panel && input) {
                            input.value = payload.share_url;
                            panel.classList.remove("hidden");
                        }
                        copyText(payload.share_url).then(function () {
                            shareButton.textContent = "Link copied";
                            window.setTimeout(function () {
                                shareButton.textContent = originalText;
                            }, 1600);
                        }).catch(function () {
                            shareButton.textContent = originalText;
                        });
                    })
                    .catch(function (error) {
                        showAlert("error", error.message);
                        shareButton.textContent = originalText;
                    })
                    .finally(function () {
                        busy = false;
                        shareButton.disabled = false;
                    });
            });
        }

        if (copyButton) {
            copyButton.addEventListener("click", function () {
                var input = root.querySelector("[data-share-link]");
                if (!input || !input.value) return;
                copyText(input.value).then(function () {
                    var original = copyButton.textContent;
                    copyButton.textContent = "Copied";
                    window.setTimeout(function () { copyButton.textContent = original; }, 1200);
                });
            });
        }

        if (downloadButton) {
            downloadButton.addEventListener("click", function () {
                if (busy) return;
                busy = true;
                downloadButton.disabled = true;
                var originalText = downloadButton.textContent;
                downloadButton.textContent = "Preparing PDF...";
                fetch(CONFIG.downloadPdfUrl, { method: "POST", body: displayOptionsPayload() })
                    .then(function (response) {
                        if (!response.ok) {
                            return response.json().then(function (payload) {
                                throw new Error(payload.message || "Could not create the PDF.");
                            });
                        }
                        return response.blob();
                    })
                    .then(function (blob) {
                        var url = URL.createObjectURL(blob);
                        var link = document.createElement("a");
                        link.href = url;
                        link.download = "comparison_report.pdf";
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        URL.revokeObjectURL(url);
                    })
                    .catch(function (error) {
                        showAlert("error", error.message);
                    })
                    .finally(function () {
                        busy = false;
                        downloadButton.disabled = false;
                        downloadButton.textContent = originalText;
                    });
            });
        }
    }

    function rerenderStoredResult() {
        if (!hasResult || busy) {
            return;
        }
        fetch(CONFIG.renderUrl, { method: "POST", body: displayOptionsPayload() })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                if (payload.status === "ok") {
                    setResultsHtml(payload.html);
                }
            })
            .catch(function () {
                /* A failed re-render leaves the previous output untouched. */
            });
    }

    function scheduleRerender() {
        window.clearTimeout(renderTimer);
        renderTimer = window.setTimeout(rerenderStoredResult, 250);
    }

    function runComparison() {
        if (busy) {
            return;
        }

        var mode = currentMode();
        var data = displayOptionsPayload();
        data.append("mode", mode);
        data.append("semantic_json", semanticJson.checked ? "true" : "false");

        var spinnerMessage;

        if (mode === "ZIP vs ZIP") {
            if (!selectedFiles.left_zip || !selectedFiles.right_zip) {
                showAlert("error", "Upload both ZIP files before comparing.");
                return;
            }
            data.append("left_zip", selectedFiles.left_zip, selectedFiles.left_zip.name);
            data.append("right_zip", selectedFiles.right_zip, selectedFiles.right_zip.name);
            spinnerMessage = "Comparing ZIP contents...";
        } else if (mode === "Folder vs Folder") {
            var leftFolder = document.getElementById("left-folder").value;
            var rightFolder = document.getElementById("right-folder").value;
            if (!leftFolder.trim() || !rightFolder.trim()) {
                showAlert("error", "Enter both folder paths before comparing.");
                return;
            }
            data.append("left_folder", leftFolder);
            data.append("right_folder", rightFolder);
            spinnerMessage = "Comparing folders...";
        } else if (mode === "File vs File") {
            if (!selectedFiles.left_file || !selectedFiles.right_file) {
                showAlert("error", "Upload both files before comparing.");
                return;
            }
            data.append("left_file", selectedFiles.left_file, selectedFiles.left_file.name);
            data.append("right_file", selectedFiles.right_file, selectedFiles.right_file.name);
            spinnerMessage = "Comparing files...";
        } else if (mode === "Text vs Text") {
            data.append("left_text", document.getElementById("left-text").value);
            data.append("right_text", document.getElementById("right-text").value);
            spinnerMessage = "Comparing text...";
        } else {
            showAlert("error", "Unsupported comparison type.");
            return;
        }

        busy = true;
        showSpinner(spinnerMessage);
        setButtonsDisabled(true);

        fetch(CONFIG.compareUrl, { method: "POST", body: data })
            .then(function (response) { return response.json(); })
            .then(function (payload) {
                if (payload.status === "ok") {
                    clearStatus();
                    hasResult = true;
                    setResultsHtml(payload.html);
                } else if (payload.status === "exception") {
                    showException(payload.message, payload.traceback);
                } else {
                    // Errors leave any previous result on screen, as before.
                    showAlert("error", payload.message || "The comparison failed.");
                }
            })
            .catch(function (error) {
                showAlert("error", "The request could not be completed: " + error.message);
            })
            .finally(function () {
                busy = false;
                setButtonsDisabled(false);
            });
    }

    function setButtonsDisabled(disabled) {
        var buttons = form.querySelectorAll('[data-action="compare"]');
        Array.prototype.forEach.call(buttons, function (button) {
            button.disabled = disabled;
        });
    }

    /* ------------------------------------------------------------------ */
    /* Wiring                                                              */
    /* ------------------------------------------------------------------ */

    Array.prototype.forEach.call(
        form.querySelectorAll('input[name="mode"]'),
        function (radio) {
            radio.addEventListener("change", applyMode);
        }
    );

    Array.prototype.forEach.call(
        form.querySelectorAll(".st-uploader"),
        initUploader
    );

    Array.prototype.forEach.call(
        form.querySelectorAll('[data-action="compare"]'),
        function (button) {
            button.addEventListener("click", runComparison);
        }
    );

    useCustomLabels.addEventListener("change", function () {
        customLabelRow.classList.toggle("hidden", !useCustomLabels.checked);
        applyLabels();
        rerenderStoredResult();
    });

    customLeftLabel.addEventListener("input", function () {
        applyLabels();
        scheduleRerender();
    });

    customRightLabel.addEventListener("input", function () {
        applyLabels();
        scheduleRerender();
    });

    showSpaces.addEventListener("change", rerenderStoredResult);

    applyLabels();
    applyMode();
})();
