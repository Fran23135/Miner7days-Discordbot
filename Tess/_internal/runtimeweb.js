#!/usr/bin/env node
// =============================================================================
// runtimeweb.js — Tesseract WebIR -> JavaScript Transpiler
// =============================================================================
// Lee el WebIR JSON generado por tessruntimeweb.py y produce codigo JS
// transpilado, valido y ejecutable directamente en browser o Node.js.
//
// Pipeline completo:
//   Parser -> AST JSON -> tessruntimeweb.py -> WebIR JSON -> runtimeweb.js -> .js
//
// Uso:
//   node runtimeweb.js programa.webir.json               -> stdout
//   node runtimeweb.js programa.webir.json -o salida.js  -> archivo
//   node runtimeweb.js programa.webir.json --run         -> transpila y ejecuta
//   node runtimeweb.js programa.webir.json -o s.js --run -> transpila, guarda y ejecuta
//
// Cubre todos los ops de tessruntimeweb.py:
//   DECL, ASSIGN, CONST, CALL, PRINT, READ, RETURN, BREAK,
//   IF (elif/else), FOR (rangos int/float/string), WHILE, DO_WHILE,
//   SWITCH (fall-through), INC/DEC pre/post,
//   PARAM_ASSIGN, ARR_SET, ARR_ACCESS, IMPORT
//   + FUTURO: OBJ_DECL, EVENT_BIND, UI_CREATE, COMPONENT_DEF
// =============================================================================

"use strict";

const fs   = require("fs");
const path = require("path");
const os   = require("os");

// =============================================================================
// Utilidades de indentacion
// =============================================================================

const INDENT = "  "; // 2 espacios por nivel

function indent(level) {
  return INDENT.repeat(level);
}

// =============================================================================
// Mapeo de modulos nativos de Tesseract -> equivalentes JS
// =============================================================================

const MODULE_MAP = {
  math:    { js: "Math",         kind: "native" },
  string:  { js: "__TessString", kind: "tess"   },
  array:   { js: "__TessArray",  kind: "tess"   },
  io:      { js: "__TessIO",     kind: "tess"   },
  time:    { js: "__TessTime",   kind: "tess"   },
  json:    { js: "JSON",         kind: "native" },
  console: { js: "console",      kind: "native" },
};

// Funciones del modulo math -> Math JS
const MATH_FN_MAP = {
  sqrt:"sqrt", pow:"pow", abs:"abs", ceil:"ceil",
  floor:"floor", round:"round", max:"max", min:"min",
  log:"log", sin:"sin", cos:"cos", tan:"tan",
  PI:"PI", E:"E",
};

// =============================================================================
// Core Type Method Map — interpre.py -> JavaScript equivalente
// Cubre todos los metodos definidos en _core_*_methods() de interpre.py.
// Cada entrada es (obj: string, args: string[]) => string JS.
// =============================================================================

const CORE_METHOD_MAP = {
  // ── Conversores de tipo ──────────────────────────────────────────────────
  typeInt:     (obj, args) => `parseInt(${obj}, 10)`,
  typeFloat:   (obj, args) => `parseFloat(${obj})`,
  typeBool:    (obj, args) => `Boolean(${obj})`,
  typeString:  (obj, args) => `String(${obj})`,

  // ── String ─────────────────────────────────────────────────────────────
  toUpperCase: (obj, args) => `${obj}.toUpperCase()`,
  toLowerCase: (obj, args) => `${obj}.toLowerCase()`,
  trim:        (obj, args) => `${obj}.trim()`,
  trimStart:   (obj, args) => `${obj}.trimStart()`,
  trimEnd:     (obj, args) => `${obj}.trimEnd()`,
  // reverse en string: no existe nativo en JS
  reverse:     (obj, args) => `Array.from(${obj}).reverse().join("")`,
  repeat:      (obj, args) => `${obj}.repeat(${args[0] || 1})`,
  // replace: Tesseract reemplaza TODAS las ocurrencias (como Python str.replace)
  replace:     (obj, args) => `${obj}.replaceAll(${args[0]}, ${args[1]})`,
  split:       (obj, args) => args.length ? `${obj}.split(${args[0]})` : `Array.from(${obj})`,
  slice:       (obj, args) => args.length >= 2
                  ? `${obj}.slice(${args[0]}, ${args[1]})`
                  : `${obj}.slice(${args[0] || 0})`,
  charAt:      (obj, args) => `${obj}.charAt(${args[0] || 0})`,
  // contains: Tesseract -> JS includes
  contains:    (obj, args) => `${obj}.includes(${args[0] !== undefined ? args[0] : '""'})`,
  startsWith:  (obj, args) => `${obj}.startsWith(${args[0] || '""'})`,
  endsWith:    (obj, args) => `${obj}.endsWith(${args[0] || '""'})`,
  indexOf:     (obj, args) => `${obj}.indexOf(${args[0] !== undefined ? args[0] : '""'})`,
  padStart:    (obj, args) => args.length >= 2
                  ? `${obj}.padStart(${args[0]}, ${args[1]})`
                  : `${obj}.padStart(${args[0] || 0})`,
  padEnd:      (obj, args) => args.length >= 2
                  ? `${obj}.padEnd(${args[0]}, ${args[1]})`
                  : `${obj}.padEnd(${args[0] || 0})`,

  // ── Number (int / float) ────────────────────────────────────────────────
  abs:         (obj, args) => `Math.abs(${obj})`,
  clamp:       (obj, args) => `Math.min(Math.max(${obj}, ${args[0]}), ${args[1]})`,
  pow:         (obj, args) => `Math.pow(${obj}, ${args[0]})`,
  max:         (obj, args) => `Math.max(${obj}, ${args[0]})`,
  min:         (obj, args) => `Math.min(${obj}, ${args[0]})`,
  round:       (obj, args) => args.length
                  ? `parseFloat(${obj}.toFixed(${args[0]}))`
                  : `Math.round(${obj})`,
  floor:       (obj, args) => `Math.floor(${obj})`,
  ceil:        (obj, args) => `Math.ceil(${obj})`,

  // ── Bool ────────────────────────────────────────────────────────────────
  toggle:      (obj, args) => `!${obj}`,

  // ── Array ───────────────────────────────────────────────────────────────
  // push retorna el nuevo array (Tesseract) vs length (JS) — emitimos como expresion
  push:        (obj, args) => `(${obj}.push(${args[0]}), ${obj})`,
  pop:         (obj, args) => `${obj}.pop()`,
  shift:       (obj, args) => `${obj}.shift()`,
  unshift:     (obj, args) => `(${obj}.unshift(${args[0]}), ${obj})`,
  insert:      (obj, args) => `[...${obj}.slice(0, ${args[0]}), ${args[1]}, ...${obj}.slice(${args[0]})]`,
  remove:      (obj, args) => `${obj}.filter((_e) => _e !== ${args[0]})`,
  clear:       (obj, args) => `(${obj}.length = 0, ${obj})`,
  sort:        (obj, args) => `[...${obj}].sort()`,
  concat:      (obj, args) => `${obj}.concat(${args[0]})`,
  join:        (obj, args) => `${obj}.join(${args[0] || '""'})`,
  // unique: no existe nativo en JS sobre arrays
  unique:      (obj, args) => `[...new Set(${obj})]`,
  // flatten: JS flat()
  flatten:     (obj, args) => `${obj}.flat()`,
};

// =============================================================================
// Core Type Property Map — propiedades de tipo core -> expresion JS
// Cubre todos los metodos cat:'first' de _core_*_methods() de interpre.py.
// =============================================================================

const CORE_PROP_MAP = {
  // Comunes
  length:      (obj) => `${obj}.length`,
  isEmpty:     (obj) => `(${obj}.length === 0)`,
  isArray:     (obj) => `Array.isArray(${obj})`,
  isString:    (obj) => `(typeof ${obj} === "string")`,
  isInt:       (obj) => `Number.isInteger(${obj})`,
  isFloat:     (obj) => `(typeof ${obj} === "number" && !Number.isInteger(${obj}))`,
  isBool:      (obj) => `(typeof ${obj} === "boolean")`,
  isNull:      (obj) => `(${obj} === null || ${obj} === undefined)`,
  type:        (obj) => `typeof ${obj}`,
  // Int / Float
  isEven:      (obj) => `(${obj} % 2 === 0)`,
  isOdd:       (obj) => `(${obj} % 2 !== 0)`,
  isPositive:  (obj) => `(${obj} > 0)`,
  isNegative:  (obj) => `(${obj} < 0)`,
  isNaN:       (obj) => `isNaN(${obj})`,
  isInfinite:  (obj) => `!isFinite(${obj})`,
  // Array
  first:       (obj) => `${obj}[0]`,
  last:        (obj) => `${obj}[${obj}.length - 1]`,
};

// =============================================================================
// ExprIR -> codigo JS
// =============================================================================

// =============================================================================
// Emitir literales de coleccion (array, dict, tuple)
// Cubre todos los tipos que interpre.py maneja en _core_array_methods y dicts
// =============================================================================

function emitLiteral(v, t, ctx) {
  // Array / Tuple
  if (t === "array" || t === "tuple" || Array.isArray(v)) {
    if (!Array.isArray(v)) return "[]";
    const items = v.map(item => {
      if (item === null || item === undefined) return "null";
      if (typeof item === "boolean")           return item ? "true" : "false";
      if (typeof item === "string")            return JSON.stringify(item);
      if (Array.isArray(item))                 return emitLiteral(item, "array", ctx);
      if (typeof item === "object")            return emitLiteral(item, "dict", ctx);
      return String(item);
    });
    return `[${items.join(", ")}]`;
  }
  // Dict / Map / Object
  if (t === "dict" || t === "map" || t === "object" ||
      (typeof v === "object" && v !== null && !Array.isArray(v))) {
    if (typeof v !== "object" || v === null) return "{}";
    const entries = Object.entries(v).map(([k, val]) => {
      let jsVal;
      if (val === null || val === undefined) jsVal = "null";
      else if (typeof val === "boolean")     jsVal = val ? "true" : "false";
      else if (typeof val === "string")      jsVal = JSON.stringify(val);
      else if (Array.isArray(val))           jsVal = emitLiteral(val, "array", ctx);
      else if (typeof val === "object")      jsVal = emitLiteral(val, "dict", ctx);
      else                                   jsVal = String(val);
      return `${JSON.stringify(k)}: ${jsVal}`;
    });
    return `{${entries.join(", ")}}`;
  }
  // Fallback
  return JSON.stringify(v);
}

function emitExpr(node, ctx) {
  
  if (!node) return "null";
  const k = node.k;
  if (k === "undefined") return "undefined";
  if (k === "lit") {
    if (node.v === null || node.v === undefined) return "null";
    if (node.t === "string")                     return JSON.stringify(node.v);
    if (node.t === "bool" || typeof node.v === "boolean") return node.v ? "true" : "false";
    // Array / Tuple / Dict — delegar a emitLiteral
    if (node.t === "array" || node.t === "tuple" || Array.isArray(node.v))
      return emitLiteral(node.v, node.t || "array", ctx);
    if (node.t === "dict" || node.t === "map" ||
        (typeof node.v === "object" && node.v !== null))
      return emitLiteral(node.v, node.t || "dict", ctx);
    return String(node.v);
  }

  if (k === "var")    return safeName(node.n);

  if (k === "binop") {
    const l = emitExpr(node.l, ctx);
    const r = emitExpr(node.r, ctx);
    return `(${l} ${node.op} ${r})`;
  }

  if (k === "logical") {
    const l = emitExpr(node.l, ctx);
    const r = emitExpr(node.r, ctx);
    return `(${l} ${node.op} ${r})`;
  }

  if (k === "unary") {
    return `${node.op}${emitExpr(node.e, ctx)}`;
  }

  if (k === "concat") {
    const parts = node.p.map(p => {
      const e = emitExpr(p, ctx);
      if (p.k === "lit" && p.t === "string") return e;
      return `String(${e})`;
    });
    return parts.join(" + ");
  }

  if (k === "call") {
    if (node.m) return emitModCall(node.m, node.fn, node.a, ctx);
    const args = (node.a || []).map(a => emitExpr(a, ctx)).join(", ");
    return `${safeName(node.n)}(${args})`;
  }

  if (k === "mcall") return emitModCall(node.m, node.fn, node.a, ctx);

  if (k === "mvar") {
    const mod = resolveModuleName(node.m, ctx);
    // Si el modulo no es conocido, puede ser una propiedad de tipo core
    if (mod === node.m && CORE_PROP_MAP[node.n]) {
      return CORE_PROP_MAP[node.n](safeName(node.m));
    }
    return `${mod}.${node.n}`;
  }

  // Propiedad de tipo core emitida como PropAccessNode (k="prop")
  if (k === "prop") {
    const obj = safeName(node.obj);
    if (CORE_PROP_MAP[node.n]) return CORE_PROP_MAP[node.n](obj);
    return `${obj}.${node.n}`;
  }

  // Llamada a metodo de tipo core emitida como MethodCallNode (k="method")
  if (k === "method") {
    const obj  = safeName(node.obj);
    const args = (node.a || []).map(a => emitExpr(a, ctx));
    if (CORE_METHOD_MAP[node.fn]) return CORE_METHOD_MAP[node.fn](obj, args);
    // Fallback: llamada directa
    return `${obj}.${node.fn}(${args.join(", ")})`;
  }

  if (k === "arr_get") {
    const name   = safeName(node.n);
    const idxStr = (node.idx || []).map(i => `[${emitExpr(i, ctx)}]`).join("");
    return `${name}${idxStr}`;
  }

  if (k === "range") return emitRange(node, ctx);

  if (k === "null")  return "null";

  return "undefined";
}

// =============================================================================
// Helpers de expresion
// =============================================================================

function emitModCall(modName, fnName, args, ctx) {
  const jsArgs = (args || []).map(a => emitExpr(a, ctx));
  // Modulo math: mapeo directo a Math
  if (modName === "math" || modName === "Math") {
    const jsFn = MATH_FN_MAP[fnName] || fnName;
    return `Math.${jsFn}(${jsArgs.join(", ")})`;
  }
  const mod = resolveModuleName(modName, ctx);
  // Si el nombre no es un modulo conocido pero la funcion es metodo core,
  // aplicar el mapa de metodos de tipo (ej: myStr.contains(...) -> myStr.includes(...))
  if (mod === modName && CORE_METHOD_MAP[fnName]) {
    return CORE_METHOD_MAP[fnName](safeName(modName), jsArgs);
  }
  return `${mod}.${fnName}(${jsArgs.join(", ")})`;
}

function resolveModuleName(name, ctx) {
  if (ctx && ctx.modules && ctx.modules[name]) {
    return ctx.modules[name].js || name;
  }
  if (MODULE_MAP[name]) return MODULE_MAP[name].js;
  return name;
}

function emitRange(node, ctx) {
  const s   = emitExpr(node.s,   ctx);
  const end = emitExpr(node.end, ctx);
  if (node.rt === "float") {
    return `Array.from({length: Math.round((${end} - ${s}) / 0.1) + 1}, (_, i) => parseFloat((${s} + i * 0.1).toFixed(10)))`;
  }
  if (node.rt === "string") {
    return `Array.from({length: ${end}.charCodeAt(0) - ${s}.charCodeAt(0) + 1}, (_, i) => String.fromCharCode(${s}.charCodeAt(0) + i))`;
  }
  return `Array.from({length: ${end} - ${s} + 1}, (_, i) => ${s} + i)`;
}

function safeName(name) {
  const JS_RESERVED = new Set([
    "abstract","arguments","await","boolean","break","byte","case","catch",
    "char","class","const","continue","debugger","default","delete","do",
    "double","else","enum","eval","export","extends","false","final",
    "finally","float","for","function","goto","if","implements","import",
    "in","instanceof","int","interface","let","long","native","new","null",
    "package","private","protected","public","return","short","static",
    "super","switch","synchronized","this","throw","throws","transient",
    "true","try","typeof","undefined","var","void","volatile","while","with",
    "yield"
  ]);
  if (JS_RESERVED.has(name)) return `_tess_${name}`;
  return name;
}

// =============================================================================
// Instruccion IR -> lineas JS
// =============================================================================

function emitInstruction(instr, level, ctx) {
  if (!instr) return [];
  const op = instr.op;
  const p  = indent(level);

  switch (op) {

    case "DECL": {
      const valIr = instr.val;
      let valStr = "";
      if (valIr && valIr.k !== "undefined") {
        valStr = ` = ${emitExpr(valIr, ctx)}`;
      }
      const comment = (instr.jst && instr.jst !== "any" && instr.jst !== "null") ? ` /*${instr.jst}*/` : "";
      return [`${p}let ${safeName(instr.n)}${comment}${valStr};`];
    }

    case "CONST": {
      const val = emitExpr(instr.val, ctx);
      return [`${p}const ${safeName(instr.n)} = ${val};`];
    }

    case "ASSIGN": {
      const val = emitExpr(instr.val, ctx);
      return [`${p}${safeName(instr.n)} = ${val};`];
    }

    case "ARR_SET": {
      const idx = emitExpr(instr.idx, ctx);
      const val = emitExpr(instr.val, ctx);
      return [`${p}${safeName(instr.n)}[${idx}] = ${val};`];
    }

    case "ARR_ACCESS": {
      const idx = emitExpr(instr.idx, ctx);
      return [`${p}${safeName(instr.n)}[${idx}];`];
    }

    case "PRINT": {
      const val = emitExpr(instr.val, ctx);
      return [`${p}console.log(${val});`];
    }

    case "READ": {
  const target = instr.target ? safeName(instr.target) : null;
  if (!target) {
    // Si no hay target, al menos advertir y asignar a una variable temporal
    console.error(`[runtimeweb] READ sin target en WebIR`);
    return [`${p}__tessRead(${prompt});  // ERROR: falta variable destino`];
  }
  const prompt = instr.prompt ? JSON.stringify(instr.prompt) : '""';
  let readExpr = ctx.htmlMode ? `await __tessRead(${prompt})` : `__tessRead(${prompt})`;
  if (instr.conv === "int")   readExpr = `parseInt(${readExpr}, 10)`;
  if (instr.conv === "float") readExpr = `parseFloat(${readExpr})`;
  if (instr.conv === "bool")  readExpr = `(${readExpr} === "true")`;
  return [`${p}${target} = ${readExpr};`];
}

    case "CALL": {
      if (instr.k === "mcall") {
        const call = emitModCall(instr.m, instr.fn, instr.a, ctx);
        return [`${p}${call};`];
      }
      const args = (instr.a || []).map(a => emitExpr(a, ctx)).join(", ");
      return [`${p}${safeName(instr.n)}(${args});`];
    }

    case "RETURN": {
      if (!instr.val) return [`${p}return;`];
      return [`${p}return ${emitExpr(instr.val, ctx)};`];
    }

    case "BREAK":
      return [`${p}break;`];

    case "IF": {
      const lines = [];
      const cond  = emitExpr(instr.cond, ctx);
      lines.push(`${p}if (${cond}) {`);
      for (const s of (instr.then || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      for (const ei of (instr.elif || [])) {
        const ec = emitExpr(ei.cond, ctx);
        lines.push(`${p}} else if (${ec}) {`);
        for (const s of (ei.body || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      }
      if (instr.else && instr.else.length > 0) {
        lines.push(`${p}} else {`);
        for (const s of instr.else) lines.push(...emitInstruction(s, level + 1, ctx));
      }
      lines.push(`${p}}`);
      return lines;
    }

    case "FOR": {
      const lines = [];
      const vn    = safeName(instr.var);
      const iter  = instr.iter;

      if (iter && iter.k === "range") {
        const s   = emitExpr(iter.s,   ctx);
        const end = emitExpr(iter.end, ctx);
        if (iter.rt === "int") {
          lines.push(`${p}for (let ${vn} = ${s}; ${vn} <= ${end}; ${vn}++) {`);
        } else {
          const arrName = `__range_${vn}`;
          lines.push(`${p}const ${arrName} = ${emitRange(iter, ctx)};`);
          lines.push(`${p}for (const ${vn} of ${arrName}) {`);
        }
      } else {
        const iterExpr = emitExpr(iter, ctx);
        lines.push(`${p}for (const ${vn} of ${iterExpr}) {`);
      }

      for (const s of (instr.body || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      lines.push(`${p}}`);
      return lines;
    }

    case "WHILE": {
      const lines = [];
      const cond  = emitExpr(instr.cond, ctx);
      lines.push(`${p}while (${cond}) {`);
      for (const s of (instr.body || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      lines.push(`${p}}`);
      return lines;
    }

    case "DO_WHILE": {
      const lines = [];
      const cond  = emitExpr(instr.cond, ctx);
      lines.push(`${p}do {`);
      for (const s of (instr.body || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      lines.push(`${p}} while (${cond});`);
      return lines;
    }

    case "SWITCH": {
      const lines = [];
      const val   = emitExpr(instr.val, ctx);
      lines.push(`${p}switch (${val}) {`);
      for (const c of (instr.cases || [])) {
        const cv   = emitExpr(c.val, ctx);
        const body = c.body || [];
        // Cada case se envuelve en {} para que los `let` de un case
        // no colisionen con los de otro (scope propio por case).
        lines.push(`${p}  case ${cv}: {`);
        for (const s of body) lines.push(...emitInstruction(s, level + 2, ctx));
        // Solo añadir break automatico si el body NO termina ya en BREAK
        // (evita el break duplicado cuando el codigo fuente ya lo tiene).
        const alreadyBreaks = body.length > 0 && body[body.length - 1].op === "BREAK";
        if (!c.fall && !alreadyBreaks) lines.push(`${p}    break;`);
        lines.push(`${p}  }`);
      }
      if (instr.default && instr.default.length > 0) {
        const dbody = instr.default;
        lines.push(`${p}  default: {`);
        for (const s of dbody) lines.push(...emitInstruction(s, level + 2, ctx));
        const defaultBreaks = dbody.length > 0 && dbody[dbody.length - 1].op === "BREAK";
        if (!defaultBreaks) lines.push(`${p}    break;`);
        lines.push(`${p}  }`);
      }
      lines.push(`${p}}`);
      return lines;
    }

    case "INC_POST":    return [`${p}${safeName(instr.n)}++;`];
    case "DEC_POST":    return [`${p}${safeName(instr.n)}--;`];
    case "INC_PRE":     return [`${p}++${safeName(instr.n)};`];
    case "DEC_PRE":     return [`${p}--${safeName(instr.n)};`];

    case "PARAM_ASSIGN": {
      const val = emitExpr(instr.val, ctx);
      return [`${p}${safeName(instr.n)} = ${val};`];
    }
    case "FUNC" : {
      return emitFunction(instr, ctx, level);
    }

    // =========================================================================
    // EXTENSION FUTURA
    // =========================================================================

    case "OBJ_DECL": {
      const lines = [];
      lines.push(`${p}class ${safeName(instr.n)} {`);
      if (instr.fields && instr.fields.length > 0) {
        lines.push(`${p}  constructor() {`);
        for (const f of instr.fields) {
          const fval = f.val ? emitExpr(f.val, ctx) : "null";
          lines.push(`${p}    this.${safeName(f.n)} = ${fval};`);
        }
        lines.push(`${p}  }`);
      }
      for (const m of (instr.methods || [])) {
        const mparams = (m.params || []).map(pm => safeName(pm.n)).join(", ");
        lines.push(`${p}  ${safeName(m.name)}(${mparams}) {`);
        for (const s of (m.body || [])) lines.push(...emitInstruction(s, level + 2, ctx));
        lines.push(`${p}  }`);
      }
      lines.push(`${p}}`);
      return lines;
    }

    case "EVENT_BIND": {
      const target  = safeName(instr.target);
      const event   = JSON.stringify(instr.event  || "click");
      const handler = safeName(instr.handler || "");
      return [`${p}${target}.addEventListener(${event}, ${handler});`];
    }

    case "UI_CREATE": {
      const lines  = [];
      const elName = safeName(instr.id);
      const tag    = JSON.stringify(instr.tag || "div");
      lines.push(`${p}const ${elName} = document.createElement(${tag});`);
      for (const [prop, val] of Object.entries(instr.props || {})) {
        lines.push(`${p}${elName}.${prop} = ${JSON.stringify(val)};`);
      }
      return lines;
    }

    case "COMPONENT_DEF": {
      const lines   = [];
      const cname   = safeName(instr.name);
      const cparams = (instr.props || []).map(pm => safeName(pm.n)).join(", ");
      lines.push(`${p}function ${cname}(${cparams}) {`);
      for (const s of (instr.body || [])) lines.push(...emitInstruction(s, level + 1, ctx));
      lines.push(`${p}}`);
      return lines;
    }

    default:
      return [`${p}/* [WebIR] op no implementada: ${op} */`];
  }
}

// =============================================================================
// Emitir funcion de usuario
// =============================================================================

function emitFunction(fn, ctx, level = 0) {
  const lines  = [];
  const p      = indent(level);
  const name   = safeName(fn.name);
  const params = (fn.params || []).map(p => {
    const comment = p.jst && p.jst !== "any" ? `/*${p.jst}*/` : "";
    return `${safeName(p.n)}${comment}`;
  }).join(", ");
  const retComment = fn.jret && fn.jret !== "any" && fn.jret !== "void"
    ? ` /*-> ${fn.jret}*/`
    : "";

  const asyncKw = ctx.htmlMode ? "async " : "";
  lines.push(`${p}${asyncKw}function ${name}(${params})${retComment} {`);
  for (const instr of (fn.body || [])) {
    lines.push(...emitInstruction(instr, level + 1, ctx));
  }
  lines.push(`${p}}`);
  return lines;
}

// =============================================================================
// Preambulo: helpers runtime que el JS generado puede necesitar
// =============================================================================

function buildPreamble(ir, ctx) {
  const lines    = [];
  const irStr    = JSON.stringify(ir);
  const usesRead = irStr.includes('"READ"');

  lines.push(`// ============================================================`);
  lines.push(`// Generado por runtimeweb.js — Tesseract WebIR Transpiler`);
  lines.push(`// tess_web_ir: ${ir.tess_web_ir}`);
  lines.push(`// ============================================================`);
  lines.push(``);

      if (usesRead) {
      lines.push(`// -- Helper lectura --`);
      if (ctx.htmlMode) {
        lines.push(`function __tessRead(promptText) {`);
        lines.push(`  return new Promise(function(resolve) {`);
        lines.push(`    var area = document.getElementById('__tess_input_area');`);
        lines.push(`    var out  = document.getElementById('output');`);
        lines.push(`    var wrapper = document.createElement('div');`);
        lines.push(`    wrapper.className = 'tess-input-line';`);
        lines.push(`    var prefix = document.createElement('span');`);
        lines.push(`    prefix.className = 'tess-input-prompt';`);
        lines.push(`    prefix.textContent = '\u203a';`);
        lines.push(`    var field = document.createElement('input');`);
        lines.push(`    field.type = 'text';`);
        lines.push(`    field.className = 'tess-input-field';`);
        lines.push(`    field.autocomplete = 'off';`);
        lines.push(`    field.spellcheck = false;`);
        lines.push(`    wrapper.appendChild(prefix);`);
        lines.push(`    wrapper.appendChild(field);`);
        lines.push(`    if (area) { area.innerHTML = ''; area.appendChild(wrapper); }`);
        lines.push(`    if (out) out.scrollTop = out.scrollHeight;`);
        lines.push(`    setTimeout(function() { field.focus(); }, 0);`);
        lines.push(`    field.addEventListener('keydown', function(e) {`);
        lines.push(`      if (e.key !== 'Enter') return;`);
        lines.push(`      var value = field.value;`);
        lines.push(`      var sent = document.createElement('div');`);
        lines.push(`      sent.className = 'tess-sent-input';`);
        lines.push(`      var sp = document.createElement('span');`);
        lines.push(`      sp.className = 'tess-sent-prompt';`);
        lines.push(`      sp.textContent = '\u203a';`);
        lines.push(`      var sv = document.createElement('span');`);
        lines.push(`      sv.className = 'tess-sent-value';`);
        lines.push(`      sv.textContent = value;`);
        lines.push(`      sent.appendChild(sp);`);
        lines.push(`      sent.appendChild(sv);`);
        lines.push(`      if (out) { out.appendChild(sent); out.scrollTop = out.scrollHeight; }`);
        lines.push(`      if (area) area.innerHTML = '';`);
        lines.push(`      resolve(value);`);
        lines.push(`    });`);
        lines.push(`  });`);
        lines.push(`}`);
      } else {
        lines.push(`function __tessRead(prompt) {`);
        lines.push(`  if (typeof process !== "undefined" && process.stdin) {`);
        lines.push(`    const { execSync } = require("child_process");`);
        lines.push(`    if (prompt) process.stdout.write(String(prompt));`);
        lines.push(`    try {`);
        lines.push(`      return execSync("head -1", {`);
        lines.push(`        stdio: ["inherit", "pipe", "inherit"]`);
        lines.push(`      }).toString().replace(/\\n$/, "");`);
        lines.push(`    } catch { return ""; }`);
        lines.push(`  }`);
        lines.push(`  return window.prompt(String(prompt) || "") || "";`);
        lines.push(`}`);
      }
      lines.push(``);
   }

  const modulesUsed = new Set((ir.modules || []).map(m => m.name));

  if (modulesUsed.has("string")) {
    lines.push(`// -- __TessString --`);
    lines.push(`const __TessString = {`);
    lines.push(`  length:   (s) => s.length,`);
    lines.push(`  upper:    (s) => s.toUpperCase(),`);
    lines.push(`  lower:    (s) => s.toLowerCase(),`);
    lines.push(`  trim:     (s) => s.trim(),`);
    lines.push(`  contains: (s, sub) => s.includes(sub),`);
    lines.push(`  replace:  (s, a, b) => s.replaceAll(a, b),`);
    lines.push(`  split:    (s, sep) => s.split(sep),`);
    lines.push(`  indexOf:  (s, sub) => s.indexOf(sub),`);
    lines.push(`  slice:    (s, start, end) => s.slice(start, end),`);
    lines.push(`  charAt:   (s, i) => s.charAt(i),`);
    lines.push(`  toInt:    (s) => parseInt(s, 10),`);
    lines.push(`  toFloat:  (s) => parseFloat(s),`);
    lines.push(`};`);
    lines.push(``);
  }

  if (modulesUsed.has("array")) {
    lines.push(`// -- __TessArray --`);
    lines.push(`const __TessArray = {`);
    lines.push(`  length:   (a) => a.length,`);
    lines.push(`  push:     (a, v) => { a.push(v); return a; },`);
    lines.push(`  pop:      (a) => a.pop(),`);
    lines.push(`  shift:    (a) => a.shift(),`);
    lines.push(`  includes: (a, v) => a.includes(v),`);
    lines.push(`  indexOf:  (a, v) => a.indexOf(v),`);
    lines.push(`  slice:    (a, s, e) => a.slice(s, e),`);
    lines.push(`  reverse:  (a) => [...a].reverse(),`);
    lines.push(`  sort:     (a) => [...a].sort(),`);
    lines.push(`  map:      (a, fn) => a.map(fn),`);
    lines.push(`  filter:   (a, fn) => a.filter(fn),`);
    lines.push(`  join:     (a, sep) => a.join(sep),`);
    lines.push(`};`);
    lines.push(``);
  }

  if (modulesUsed.has("time")) {
    lines.push(`// -- __TessTime --`);
    lines.push(`const __TessTime = {`);
    lines.push(`  now:   () => Date.now(),`);
    lines.push(`  sleep: (ms) => new Promise(r => setTimeout(r, ms)),`);
    lines.push(`};`);
    lines.push(``);
  }

  return lines;
}

// =============================================================================
// Transpilador principal
// =============================================================================

function transpile(ir,opts = {}) {
  const ctx = {
    modules: {},
    htmlMode: opts.htmlMode || false,
  };

  for (const mod of (ir.modules || [])) {
    const mapped = MODULE_MAP[mod.name] || { js: mod.name, kind: "tess" };
    ctx.modules[mod.name] = { ...mapped, ...mod };
  }

  const lines = [];
  
  lines.push(...buildPreamble(ir, ctx));

  // ==========================================================================
  // Emision en orden estricto de llegada (ir.main)
  // Las funciones se emiten INLINE en la posicion donde fueron declaradas,
  // respetando el orden del codigo fuente original.
  // No se realiza ninguna reordenacion ni hoisting de funciones.
  //
  // Nota: ir.functions (seccion separada, legado) se emite SOLO si el IR
  // explicitamente la incluye; tessruntimeweb.py no la usa actualmente.
  // ==========================================================================

  // Seccion legado: ir.functions (solo si existe y tiene contenido)
  if ((ir.functions || []).length > 0) {
    lines.push(`// -- Funciones (seccion legado) --`);
    for (const fn of ir.functions) {
      lines.push(...emitFunction(fn, ctx, 0));
      lines.push(``);
    }
  }

  // Cuerpo principal: emision en orden, FUNC ops incluidos inline
  lines.push(`// -- Programa --`);
  if (ctx.htmlMode) lines.push(`(async function () {`);
  for (const instr of (ir.main || [])) {
    lines.push(...emitInstruction(instr, ctx.htmlMode ? 1 : 0, ctx));
  }
  if (ctx.htmlMode) lines.push(`})();`);

  return lines.join("\n");
}

// =============================================================================
// CLI
// =============================================================================

function printHelp() {
  console.log(`
Uso:
  node runtimeweb.js <archivo.webir.json> [opciones]

Opciones:
  -o <salida.js>   Guardar JS transpilado en archivo
  --run            Ejecutar el JS generado despues de transpilar
  --help           Mostrar esta ayuda
  -html            Generar __tessRead con input HTML en vez de window.prompt (para usar en navegadores, requiere que el HTML tenga un contenedor con id="__tess_input_area" para los inputs)
yy
Ejemplos:
  node runtimeweb.js prog.webir.json
  node runtimeweb.js prog.webir.json -o prog.js
  node runtimeweb.js prog.webir.json --run
  node runtimeweb.js prog.webir.json -o prog.js --run
`);
}

function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes("--help")) {
    printHelp();
    process.exit(0);
  }

  const inputFile = args[0];
  if (!fs.existsSync(inputFile)) {
    console.error(`[runtimeweb] ERROR: No existe '${inputFile}'`);
    process.exit(1);
  }

  let outputFile = null;
  let runAfter   = false;
  let htmlMode   = false;

  for (let i = 1; i < args.length; i++) {
    if (args[i] === "-o" && args[i + 1]) { outputFile = args[++i]; }
    else if (args[i] === "--run")         { runAfter = true; }
    else if (args[i] === "-html")         { htmlMode = true; }
  }
  let ir;
  try {
    ir = JSON.parse(fs.readFileSync(inputFile, "utf8"));
  } catch (e) {
    console.error(`[runtimeweb] ERROR leyendo WebIR: ${e.message}`);
    process.exit(1);
  }

  if (!ir.tess_web_ir) {
    console.error(`[runtimeweb] ERROR: archivo no es WebIR valido (falta 'tess_web_ir')`);
    process.exit(1);
  }

  let jsCode;
  try {
    jsCode = transpile(ir, { htmlMode });
  } catch (e) {
    console.error(`[runtimeweb] ERROR en transpilacion: ${e.message}`);
    console.error(e.stack);
    process.exit(1);
  }

  if (outputFile) {
    fs.writeFileSync(outputFile, jsCode, "utf8");
    console.error(`[runtimeweb] JS -> ${outputFile}`);
  } else {
    console.log(jsCode);
  }

  if (runAfter) {
    const target = outputFile || (() => {
      const tmp = path.join(os.tmpdir(), `_tess_${Date.now()}.js`);
      fs.writeFileSync(tmp, jsCode, "utf8");
      return tmp;
    })();
    console.error(`\n[runtimeweb] Ejecutando: node ${target}\n`);
    const { execFileSync } = require("child_process");
    try {
      execFileSync("node", [target], { stdio: "inherit" });
    } catch (e) {
      process.exit(e.status || 1);
    }
  }
}

main();