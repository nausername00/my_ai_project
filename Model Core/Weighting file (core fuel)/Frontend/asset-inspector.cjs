"use strict";

const MAX_STRUCTURED_JSON_BYTES = 5 * 1024 * 1024;
const IMAGE_EXTENSIONS = new Set([
  ".bmp", ".jpeg", ".jpg", ".png", ".tga", ".webp",
]);

function fileExtension(fileName) {
  const normalized = String(fileName || "").replace(/\\/g, "/").toLowerCase();
  if (normalized.endsWith(".model3.json")) return ".model3.json";
  if (normalized.endsWith(".physics3.json")) return ".physics3.json";
  const baseName = normalized.slice(normalized.lastIndexOf("/") + 1);
  const dot = baseName.lastIndexOf(".");
  return dot > 0 ? baseName.slice(dot) : "";
}

function imageSignature(extension, bytes) {
  if (extension === ".png") {
    return bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  }
  if (extension === ".jpg" || extension === ".jpeg") {
    return bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  }
  if (extension === ".webp") {
    return bytes.length >= 12 &&
      bytes.toString("ascii", 0, 4) === "RIFF" &&
      bytes.toString("ascii", 8, 12) === "WEBP";
  }
  if (extension === ".bmp") return bytes.toString("ascii", 0, 2) === "BM";
  return null;
}

function collectReferences(value, depth = 0) {
  if (depth > 8 || value === null || typeof value !== "object") return [];
  const references = [];
  for (const child of Object.values(value)) {
    if (typeof child === "string") references.push(child);
    else if (child && typeof child === "object") {
      references.push(...collectReferences(child, depth + 1));
    }
  }
  return references;
}

function inspectAsset({ fileName, bytes, byteLength = bytes?.length, selectedFileNames = [] }) {
  if (typeof fileName !== "string" || !Buffer.isBuffer(bytes)) {
    throw new TypeError("fileName and Buffer bytes are required");
  }
  const extension = fileExtension(fileName);
  const report = {
    fileName,
    format: "其他资源",
    capability: "仅本地复制与登记；未验证专用解析器",
    details: [`${byteLength} 字节`],
    warnings: [],
  };

  if (extension === ".psd") {
    report.format = "PSD";
    report.capability = "可检查文件签名并登记；图层解析与 PSD 写出尚未接入";
    report.details.push(
      bytes.length >= 4 && bytes.toString("ascii", 0, 4) === "8BPS"
        ? "PSD 签名存在（不代表图层结构已验证）"
        : "PSD 签名无效或文件已截断",
    );
    if (bytes.length < 4 || bytes.toString("ascii", 0, 4) !== "8BPS") {
      report.warnings.push("文件内容未通过 PSD 签名检查");
    }
  } else if (extension === ".model3.json" || extension === ".physics3.json") {
    report.format = extension === ".model3.json" ? "Live2D model3.json" : "Live2D physics3.json";
    report.capability = "可解析 JSON 结构与引用清单；不执行内容、不启动模型";
    if (bytes.length > MAX_STRUCTURED_JSON_BYTES) {
      report.warnings.push("超过 5 MB 结构解析上限，仅登记文件，不解析 JSON");
    } else {
      try {
        const parsed = JSON.parse(bytes.toString("utf8"));
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new TypeError("JSON 根节点必须是对象");
        }
        report.details.push(`顶层字段：${Object.keys(parsed).slice(0, 30).join(", ") || "无"}`);
        if (extension === ".model3.json") {
          if (!parsed.FileReferences || typeof parsed.FileReferences !== "object" ||
              Array.isArray(parsed.FileReferences)) {
            report.warnings.push("缺少有效的 FileReferences 对象；仅完成 JSON 语法解析");
          }
          const references = collectReferences(parsed.FileReferences || {});
          const selected = new Set(selectedFileNames.map((name) =>
            String(name).replace(/\\/g, "/").split("/").pop().toLowerCase(),
          ));
          const missing = references.filter((reference) =>
            !selected.has(String(reference).replace(/\\/g, "/").split("/").pop().toLowerCase()),
          );
          report.details.push(`声明资源引用：${references.length} 项`);
          if (references.some((reference) => /[\\/]/.test(reference))) {
            report.warnings.push(
              "资源包含相对目录引用；本次导入会平铺文件，路径可能无法在运行时解析",
            );
          }
          if (missing.length) {
            report.warnings.push(
              `所选文件中未找到 ${missing.length} 个引用：${missing.slice(0, 8).join(", ")}`,
            );
          }
        } else {
          const settings = Array.isArray(parsed.PhysicsSettings)
            ? parsed.PhysicsSettings.length
            : 0;
          report.details.push(`PhysicsSettings：${settings} 项`);
          if (!Array.isArray(parsed.PhysicsSettings)) {
            report.warnings.push("缺少 PhysicsSettings 数组；仅完成 JSON 语法解析");
          }
        }
      } catch (error) {
        report.warnings.push(`JSON 结构无法解析：${error.message}`);
      }
    }
  } else if (extension === ".moc3") {
    report.format = "Live2D moc3";
    report.capability = "仅作为不透明二进制登记；不解析、不修改、不运行";
    report.details.push("内部结构与授权 SDK 支持情况未验证");
  } else if (IMAGE_EXTENSIONS.has(extension)) {
    report.format = "贴图 / 图像素材";
    report.capability = "可按文件登记；本轮只检查常见格式签名，不解码、不判断实际用途";
    const valid = imageSignature(extension, bytes);
    if (valid === false) report.warnings.push("文件扩展名与图像签名不匹配或文件已截断");
    if (valid === null) report.details.push("此格式尚无签名检查器");
    report.details.push("批量选择的图片会被平铺保存，目录层级不会保留");
  } else if (extension === ".mov") {
    report.format = "QuickTime / MOV";
    report.capability = "仅按文件登记；媒体元数据读取、解码与转码尚未接入";
    report.details.push("未读取媒体轨道或帧率");
  } else {
    report.details.push("专用结构检查尚未接入");
  }

  return report;
}

function formatAssetReport(report) {
  const warningText = report.warnings.length
    ? `；注意：${report.warnings.join("；")}`
    : "";
  const text = `${report.fileName} · ${report.format}：${report.capability}。${report.details.join("；")}${warningText}`;
  return text.length > 700 ? `${text.slice(0, 697)}...` : text;
}

module.exports = { inspectAsset, formatAssetReport };
