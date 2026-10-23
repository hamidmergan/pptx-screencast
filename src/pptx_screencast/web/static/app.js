const $ = (id) => document.getElementById(id);

const state = {
  deck: null,
  scriptFile: null,
  scripts: [],
  slides: 0,
  step: 1,
  timer: null,
};

const STEP_LABELS = {
  scripts: "Generating scripts",
  translate: "Translating the scripts",
  speak: "Speech synthesis",
  video: "Rendering video clips",
  subtitles: "Embedding subtitles",
  join: "Joining videos",
};

function show(step) {
  state.step = step;
  for (let i = 1; i <= 4; i += 1) {
    $(`step-${i}`).hidden = i !== step;
  }
  document.querySelectorAll(".steps .step").forEach((el) => {
    const n = Number(el.dataset.step);
    el.classList.toggle("current", n === step);
    el.classList.toggle("done", n < step);
  });
}

function fail(id, message) {
  const box = $(id);
  box.textContent = message;
  box.hidden = !message;
}

function words(text) {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

// -- Settings of the page --

async function loadInfo() {
  const info = await (await fetch("/api/info")).json();
  $("base-url").value = info.base_url || "";
  $("model").value = info.model || "";
  $("tts-base-url").value = info.tts_base_url || "";
  $("tts-model").value = info.tts_model || "";
  $("stt-base-url").value = info.stt_base_url || "";
  $("stt-model").value = info.stt_model || "";
  $("voice").value = info.voice || "";
  $("language").value = info.language || "";
  $("speed").value = info.speed;
  $("slide-pause").value = info.slide_pause;
  $("resolution").value = String(info.resolution);
  $("subtitles").checked = Boolean(info.subtitles);
  $("burn-in").checked = Boolean(info.burn_in);
  if (info.has_key) $("api-key").placeholder = "set on the server";
  if (info.missing_tools && info.missing_tools.length) {
    fail("tools-warning",
      "Missing programs on the server: " + info.missing_tools.join(", ") +
      ". The scripts still work, the video does not.");
  }
}

function serverFields(form) {
  form.append("base_url", $("base-url").value);
  form.append("model", $("model").value);
  form.append("api_key", $("api-key").value);
}

// -- File pickers --

function pick(dropId, inputId, chosenId, onPick) {
  const drop = $(dropId);
  const input = $(inputId);
  input.addEventListener("change", () => {
    if (input.files.length) onPick(input.files[0]);
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    if (e.dataTransfer.files.length) onPick(e.dataTransfer.files[0]);
  });
  return (file) => {
    const box = $(chosenId);
    box.textContent = file ? file.name : "";
    box.hidden = !file;
  };
}

const showDeck = pick("drop", "file", "chosen", (f) => {
  state.deck = f;
  showDeck(f);
  fail("step1-error", "");
});

const showScript = pick("script-drop", "script-file", "script-chosen", (f) => {
  state.scriptFile = f;
  showScript(f);
});

document.querySelectorAll('input[name="source"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    $("import-pane").hidden = source() !== "import";
  });
});

function source() {
  return document.querySelector('input[name="source"]:checked').value;
}

// -- Step 1: the scripts --

$("to-scripts").addEventListener("click", async () => {
  fail("step1-error", "");
  if (!state.deck) {
    fail("step1-error", "Please select a presentation first.");
    return;
  }
  if (source() === "import" && !state.scriptFile) {
    fail("step1-error", "Please select a script file first.");
    return;
  }
  const form = new FormData();
  form.append("file", state.deck);
  form.append("source", source());
  form.append("language", $("language").value);
  form.append("translate", $("translate").value);
  serverFields(form);
  if (state.scriptFile) form.append("script_file", state.scriptFile);

  $("to-scripts").disabled = true;
  $("step1-progress").hidden = false;
  $("step1-progress").textContent = "Analyzing slides...";
  const response = await fetch("/api/scripts", { method: "POST", body: form });
  if (!response.ok) {
    $("to-scripts").disabled = false;
    $("step1-progress").hidden = true;
    fail("step1-error", await message(response));
    return;
  }
  poll(onScriptsDone, "step1-error", "step1-progress", "to-scripts");
});

async function message(response) {
  try {
    const body = await response.json();
    return body.detail || "Unknown error. Please try again.";
  } catch (e) {
    return "Unknown error. Please try again.";
  }
}

function poll(done, errorId, progressId, buttonId) {
  clearInterval(state.timer);
  state.timer = setInterval(async () => {
    const job = await (await fetch("/api/job")).json();
    if (job.state === "running") {
      const label = STEP_LABELS[job.step] || "Working";
      const count = job.total ? ` ${job.done} of ${job.total}` : "";
      if (progressId) $(progressId).textContent = `${label}${count}...`;
      return;
    }
    clearInterval(state.timer);
    if (buttonId) $(buttonId).disabled = false;
    if (progressId) $(progressId).hidden = true;
    if (job.state === "error") {
      fail(errorId, job.error || "Unknown error. Please try again.");
      return;
    }
    done(job);
  }, 1000);
}

function onScriptsDone(job) {
  state.scripts = job.scripts;
  state.slides = job.slides;
  drawScripts();
  show(2);
}

// -- Step 2: review --

function drawScripts() {
  const box = $("scripts");
  box.textContent = "";
  state.scripts.forEach((script, index) => {
    const wrap = document.createElement("div");
    wrap.className = "slide";

    const head = document.createElement("div");
    head.className = "head";
    const name = document.createElement("strong");
    name.textContent = `Slide ${index + 1}`;
    const count = document.createElement("span");
    count.className = "muted";
    head.append(name, count);

    const area = document.createElement("textarea");
    area.value = script;
    area.setAttribute("aria-label", `Script for slide ${index + 1}`);
    const update = () => {
      state.scripts[index] = area.value;
      const n = words(area.value);
      count.textContent = n
        ? `approx. ${n} words, ~${Math.round(n / 2.5)} sec`
        : "No script (empty slide)";
    };
    area.addEventListener("input", update);
    update();

    wrap.append(head, area);
    box.append(wrap);
  });
}

$("back-to-1").addEventListener("click", () => show(1));
$("to-settings").addEventListener("click", () => show(3));
$("back-to-2").addEventListener("click", () => show(2));

$("subtitles").addEventListener("change", () => {
  if (!$("subtitles").checked) $("burn-in").checked = false;
});
$("burn-in").addEventListener("change", () => {
  if ($("burn-in").checked) $("subtitles").checked = true;
});

// -- Step 3: render --

$("render").addEventListener("click", async () => {
  fail("step3-error", "");
  const form = new FormData();
  state.scripts.forEach((script) => form.append("scripts", script));
  form.append("voice", $("voice").value);
  form.append("speed", $("speed").value);
  form.append("language", $("language").value);
  form.append("slide_pause", $("slide-pause").value);
  form.append("resolution", $("resolution").value);
  form.append("slides", $("slides").value);
  // Always explicit, so an unticked box really switches the option off.
  form.append("subtitles", $("subtitles").checked ? "on" : "off");
  form.append("burn_in", $("burn-in").checked ? "on" : "off");
  serverFields(form);
  form.append("tts_base_url", $("tts-base-url").value);
  form.append("tts_model", $("tts-model").value);
  form.append("tts_api_key", $("tts-api-key").value);
  form.append("stt_base_url", $("stt-base-url").value);
  form.append("stt_model", $("stt-model").value);
  form.append("stt_api_key", $("stt-api-key").value);

  const response = await fetch("/api/render", { method: "POST", body: form });
  if (!response.ok) {
    fail("step3-error", await message(response));
    return;
  }
  fail("step4-error", "");
  $("result-heading").textContent = "Creating video...";
  $("video").hidden = true;
  $("downloads").hidden = true;
  $("render-progress").hidden = false;
  show(4);
  poll(onVideoDone, "step4-error", "render-progress", null);
});

function onVideoDone(job) {
  $("result-heading").textContent = "Done. Your screencast is ready.";
  const video = $("video");
  video.src = `/api/video?t=${Date.now()}`;
  video.hidden = false;
  $("download-srt").hidden = !job.has_subtitles;
  $("downloads").hidden = false;
}

$("again").addEventListener("click", () => {
  state.deck = null;
  state.scriptFile = null;
  state.scripts = [];
  showDeck(null);
  showScript(null);
  $("file").value = "";
  $("script-file").value = "";
  fail("step1-error", "");
  show(1);
});

loadInfo();
show(1);
