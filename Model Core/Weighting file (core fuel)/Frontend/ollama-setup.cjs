function createOllamaSetup(baseUrl, modelName, fetchImpl = fetch) {
  const base = baseUrl.replace(/\/+$/, "");

  async function getModelStatus() {
    try {
      const response = await fetchImpl(`${base}/api/tags`, {
        signal: AbortSignal.timeout(3000),
      });
      if (!response.ok) {
        return {
          serviceAvailable: false,
          modelAvailable: false,
          modelName,
          message: `Ollama returned HTTP ${response.status}`,
        };
      }
      const result = await response.json();
      const models = Array.isArray(result.models) ? result.models : [];
      const modelAvailable = models.some(
        (model) => model && model.name === modelName,
      );
      return {
        serviceAvailable: true,
        modelAvailable,
        modelName,
        message: modelAvailable ? "模型已就绪" : "尚未下载所选模型",
      };
    } catch (error) {
      return {
        serviceAvailable: false,
        modelAvailable: false,
        modelName,
        message: `无法连接 Ollama：${error.message}`,
      };
    }
  }

  async function pullModel(onProgress = () => {}) {
    const response = await fetchImpl(`${base}/api/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: modelName, stream: true }),
      signal: AbortSignal.timeout(30 * 60 * 1000),
    });
    if (!response.ok) {
      const details = await response.text();
      throw new Error(
        details || `Ollama returned HTTP ${response.status} while downloading`,
      );
    }
    if (!response.body) {
      throw new Error("Ollama did not return a model download stream");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let completed = false;

    function processLine(line) {
      if (!line.trim()) return;
      let item;
      try {
        item = JSON.parse(line);
      } catch (error) {
        throw new Error(`Ollama returned invalid download progress: ${error.message}`);
      }
      if (item.error) throw new Error(item.error);
      const progress = {
        status: typeof item.status === "string" ? item.status : "正在下载模型",
        completed:
          Number.isFinite(item.completed) && item.completed >= 0
            ? item.completed
            : null,
        total:
          Number.isFinite(item.total) && item.total > 0 ? item.total : null,
      };
      onProgress(progress);
      if (progress.status === "success") completed = true;
    }

    try {
      while (true) {
        const { done, value } = await reader.read();
        pending += decoder.decode(value, { stream: !done });
        const lines = pending.split(/\r?\n/);
        pending = lines.pop() || "";
        for (const line of lines) processLine(line);
        if (done) break;
      }
      processLine(pending);
    } finally {
      reader.releaseLock();
    }

    if (!completed) {
      throw new Error("Ollama ended the download without confirming completion");
    }
    const status = await getModelStatus();
    if (!status.modelAvailable) {
      throw new Error("Download finished, but Ollama does not list the model yet");
    }
    return status;
  }

  return { getModelStatus, pullModel };
}

module.exports = { createOllamaSetup };
