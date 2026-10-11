"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");

const { formatAssetReport, inspectAsset } = require("./asset-inspector.cjs");

test("reports PSD and moc3 limits without claiming to parse proprietary assets", () => {
  const psd = inspectAsset({ fileName: "portrait.psd", bytes: Buffer.from("8BPSdata") });
  assert.equal(psd.format, "PSD");
  assert.match(psd.capability, /图层解析与 PSD 写出尚未接入/);
  assert.match(psd.details[1], /签名存在/);

  const moc = inspectAsset({ fileName: "character.moc3", bytes: Buffer.from([0, 1, 2]) });
  assert.match(moc.capability, /不透明二进制/);
  assert.match(moc.capability, /不解析、不修改、不运行/);
});

test("parses model3 JSON references without executing them and reports missing selections", () => {
  const bytes = Buffer.from(JSON.stringify({
    Version: 3,
    FileReferences: {
      Moc: "character.moc3",
      Textures: ["textures/texture_00.png"],
      Motions: { idle: [{ File: "motions/idle.motion3.json" }] },
    },
  }));
  const report = inspectAsset({
    fileName: "character.model3.json",
    bytes,
    selectedFileNames: ["character.model3.json", "character.moc3", "texture_00.png"],
  });

  assert.equal(report.format, "Live2D model3.json");
  assert.match(report.details.join(" "), /声明资源引用：3 项/);
  assert.match(report.warnings.join(" "), /idle\.motion3\.json/);
  assert.doesNotMatch(report.warnings.join(" "), /texture_00\.png/);
});

test("reports malformed and oversized JSON instead of silently accepting it", () => {
  const malformed = inspectAsset({
    fileName: "character.physics3.json",
    bytes: Buffer.from("{not json"),
  });
  assert.match(malformed.warnings.join(" "), /JSON 结构无法解析/);

  const oversized = inspectAsset({
    fileName: "character.model3.json",
    bytes: Buffer.alloc(5 * 1024 * 1024 + 1),
  });
  assert.match(oversized.warnings.join(" "), /5 MB 结构解析上限/);

  const incompleteModel = inspectAsset({
    fileName: "character.model3.json",
    bytes: Buffer.from('{"Version":3}'),
  });
  assert.match(incompleteModel.warnings.join(" "), /缺少有效的 FileReferences/);

  const validPhysics = inspectAsset({
    fileName: "character.physics3.json",
    bytes: Buffer.from(JSON.stringify({ Meta: {}, PhysicsSettings: [{ Id: "Physics1" }] })),
  });
  assert.match(validPhysics.details.join(" "), /PhysicsSettings：1 项/);
  assert.equal(validPhysics.warnings.length, 0);
});

test("checks common image signatures and states that texture purpose is not inferred", () => {
  const validPng = inspectAsset({
    fileName: "texture.png",
    bytes: Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  });
  assert.equal(validPng.warnings.length, 0);
  assert.match(validPng.capability, /不判断实际用途/);

  const fakePng = inspectAsset({
    fileName: "texture.png",
    bytes: Buffer.from("not png"),
  });
  assert.match(fakePng.warnings.join(" "), /签名不匹配/);
});

test("identifies MOV and reports that decoding and frame-rate inspection are unavailable", () => {
  const report = inspectAsset({
    fileName: "reference.mov",
    bytes: Buffer.from("ftyp"),
  });
  assert.equal(report.format, "QuickTime / MOV");
  assert.match(formatAssetReport(report), /未读取媒体轨道或帧率/);
});
