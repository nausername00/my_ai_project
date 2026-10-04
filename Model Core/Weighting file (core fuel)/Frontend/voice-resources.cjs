const { randomUUID } = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");

const MAX_VOICE_SAMPLE_BYTES = 25 * 1024 * 1024;
const VOICE_LANGUAGES = new Set([
  "auto",
  "zh-CN",
  "en-US",
  "ja-JP",
  "ko-KR",
  "fr-FR",
  "de-DE",
  "es-ES",
]);

function getVoiceAudioType(extension, bytes) {
  if (extension === ".wav") {
    if (
      bytes.byteLength >= 12 &&
      bytes.toString("ascii", 0, 4) === "RIFF" &&
      bytes.toString("ascii", 8, 12) === "WAVE"
    ) {
      return "audio/wav";
    }
  } else if (extension === ".mp3") {
    if (
      bytes.byteLength >= 10 &&
      (bytes.toString("ascii", 0, 3) === "ID3" ||
        (bytes[0] === 0xff &&
          (bytes[1] & 0xe0) === 0xe0 &&
          (bytes[1] & 0x06) !== 0))
    ) {
      return "audio/mpeg";
    }
  }
  throw new Error("声音样本内容与 WAV / MP3 扩展名不匹配");
}

function validateVoiceMetadata(name, language) {
  if (typeof name !== "string" || !name.trim() || name.trim().length > 60) {
    throw new Error("声线名称须为 1 到 60 个字符");
  }
  if (typeof language !== "string" || !VOICE_LANGUAGES.has(language)) {
    throw new Error("声线语言不受支持");
  }
  return { name: name.trim(), language };
}

class VoiceResourceStore {
  constructor(assetDirectory) {
    this.assetDirectory = path.resolve(assetDirectory);
    this.sampleDirectory = path.join(this.assetDirectory, "voice-references");
    this.catalogPath = path.join(this.assetDirectory, "voice-resources.json");
    this.lock = Promise.resolve();
  }

  async withLock(operation) {
    const previous = this.lock;
    let release;
    this.lock = new Promise((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }

  async readCatalog() {
    let raw;
    try {
      raw = await fs.readFile(this.catalogPath, "utf8");
    } catch (error) {
      if (error.code === "ENOENT") return [];
      throw new Error(`无法读取声线资源清单：${error.message}`);
    }
    let catalog;
    try {
      catalog = JSON.parse(raw);
    } catch (error) {
      throw new Error(`声线资源清单不是有效 JSON：${error.message}`);
    }
    if (
      !catalog ||
      catalog.version !== 1 ||
      !Array.isArray(catalog.resources)
    ) {
      throw new Error("声线资源清单格式无效");
    }
    for (const resource of catalog.resources) {
      if (
        !resource ||
        typeof resource.id !== "string" ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(resource.id) ||
        typeof resource.name !== "string" ||
        !resource.name.trim() ||
        !VOICE_LANGUAGES.has(resource.language) ||
        ![".wav", ".mp3"].includes(resource.extension) ||
        resource.file !== `${resource.id}${resource.extension}` ||
        typeof resource.originalName !== "string" ||
        typeof resource.createdAt !== "string"
      ) {
        throw new Error("声线资源清单包含无效条目");
      }
    }
    return catalog.resources;
  }

  async writeCatalog(resources) {
    await fs.mkdir(this.assetDirectory, { recursive: true });
    const temporaryPath = `${this.catalogPath}.${randomUUID()}.tmp`;
    try {
      await fs.writeFile(
        temporaryPath,
        `${JSON.stringify({ version: 1, resources }, null, 2)}\n`,
        { encoding: "utf8", flag: "wx" },
      );
      await fs.rename(temporaryPath, this.catalogPath);
    } catch (error) {
      try {
        await fs.rm(temporaryPath, { force: true });
      } catch (cleanupError) {
        throw new Error(
          `无法保存声线资源清单：${error.message}；临时文件清理失败：${cleanupError.message}`,
        );
      }
      throw new Error(`无法保存声线资源清单：${error.message}`);
    }
  }

  async list() {
    return this.withLock(() => this.readCatalog());
  }

  async register({ name, language, originalName, bytes }) {
    const metadata = validateVoiceMetadata(name, language);
    if (typeof originalName !== "string" || path.basename(originalName) !== originalName) {
      throw new Error("声音样本文件名无效");
    }
    const extension = path.extname(originalName).toLowerCase();
    if (![".wav", ".mp3"].includes(extension)) {
      throw new Error("声音样本仅支持 WAV 或 MP3");
    }
    if (!(bytes instanceof Uint8Array) || bytes.byteLength < 1) {
      throw new Error("声音样本为空或无效");
    }
    if (bytes.byteLength > MAX_VOICE_SAMPLE_BYTES) {
      throw new Error("声音样本不能超过 25 MB");
    }
    const source = Buffer.from(bytes);
    const contentType = getVoiceAudioType(extension, source);

    return this.withLock(async () => {
      const resources = await this.readCatalog();
      const id = randomUUID();
      const file = `${id}${extension}`;
      await fs.mkdir(this.sampleDirectory, { recursive: true });
      await fs.writeFile(path.join(this.sampleDirectory, file), source, {
        flag: "wx",
      });
      const resource = {
        id,
        ...metadata,
        originalName,
        extension,
        contentType,
        file,
        sizeBytes: source.byteLength,
        createdAt: new Date().toISOString(),
      };
      try {
        await this.writeCatalog([...resources, resource]);
      } catch (error) {
        await fs.rm(path.join(this.sampleDirectory, file), { force: true });
        throw error;
      }
      return resource;
    });
  }

  async readSample(id) {
    if (
      typeof id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
    ) {
      throw new Error("声线资源编号无效");
    }
    return this.withLock(async () => {
      const resource = (await this.readCatalog()).find((item) => item.id === id);
      if (!resource) throw new Error("找不到该声线参考音频");
      const samplePath = path.join(this.sampleDirectory, resource.file);
      const bytes = await fs.readFile(samplePath);
      if (
        bytes.byteLength < 1 ||
        bytes.byteLength > MAX_VOICE_SAMPLE_BYTES ||
        getVoiceAudioType(resource.extension, bytes) !== resource.contentType
      ) {
        throw new Error("声线参考音频文件无效");
      }
      return { bytes, contentType: resource.contentType };
    });
  }

  async remove(id) {
    if (
      typeof id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
    ) {
      throw new Error("声线资源编号无效");
    }
    return this.withLock(async () => {
      const resources = await this.readCatalog();
      const resource = resources.find((item) => item.id === id);
      if (!resource) throw new Error("找不到该声线资源");
      const samplePath = path.join(this.sampleDirectory, resource.file);
      const archivedPath = `${samplePath}.${randomUUID()}.deleting`;
      await fs.rename(samplePath, archivedPath);
      try {
        await this.writeCatalog(resources.filter((item) => item.id !== id));
      } catch (error) {
        await fs.rename(archivedPath, samplePath).catch((restoreError) => {
          throw new Error(
            `${error.message}；恢复参考音频失败：${restoreError.message}`,
          );
        });
        throw error;
      }
      try {
        await fs.rm(archivedPath);
      } catch (error) {
        throw new Error(`声线已从资源库移除，但临时音频清理失败：${error.message}`);
      }
      return { removed: true };
    });
  }
}

module.exports = {
  MAX_VOICE_SAMPLE_BYTES,
  VOICE_LANGUAGES,
  VoiceResourceStore,
  getVoiceAudioType,
  validateVoiceMetadata,
};
