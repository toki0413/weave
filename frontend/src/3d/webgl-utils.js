// ============ WEBGL UTILITIES ============
// Native WebGL helpers — no Three.js dependency

/**
 * Compile a shader from source string
 */
export function createShader(gl, type, source) {
  var shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    var info = gl.getShaderInfoLog(shader);
    console.error('Shader compile error:', info);
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

/**
 * Link vertex and fragment shaders into a program
 */
export function createProgram(gl, vs, fs) {
  var program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    var info = gl.getProgramInfoLog(program);
    console.error('Program link error:', info);
    gl.deleteProgram(program);
    return null;
  }
  return program;
}

/**
 * Create a GPU buffer from typed array data
 */
export function createBuffer(gl, data, target, usage) {
  target = target || gl.ARRAY_BUFFER;
  usage = usage || gl.STATIC_DRAW;
  var buffer = gl.createBuffer();
  gl.bindBuffer(target, buffer);
  gl.bufferData(target, data, usage);
  return buffer;
}

/**
 * Resize canvas to match CSS display size, accounting for device pixel ratio
 */
export function resizeCanvasToDisplaySize(canvas, maxPixelRatio) {
  maxPixelRatio = maxPixelRatio || 2;
  var dpr = Math.min(window.devicePixelRatio || 1, maxPixelRatio);
  var displayWidth = Math.floor(canvas.clientWidth * dpr);
  var displayHeight = Math.floor(canvas.clientHeight * dpr);
  if (canvas.width !== displayWidth || canvas.height !== displayHeight) {
    canvas.width = displayWidth;
    canvas.height = displayHeight;
    return true;
  }
  return false;
}

// ============ BASIC SHADERS ============

export var BASIC_VERTEX_SHADER = `
attribute vec3 aPosition;
attribute vec3 aNormal;

uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
uniform mat4 uNormalMatrix;

varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vNormal = mat3(uNormalMatrix) * aNormal;
  vPosition = aPosition;
  gl_Position = uProjectionMatrix * uModelViewMatrix * vec4(aPosition, 1.0);
}
`;

export var BASIC_FRAGMENT_SHADER = `
precision mediump float;

uniform vec4 uColor;
uniform vec3 uLightDirection;
uniform float uFogNear;
uniform float uFogFar;
uniform vec3 uFogColor;
uniform float uOpacity;

varying vec3 vNormal;
varying vec3 vPosition;

void main() {
  vec3 normal = normalize(vNormal);
  float light = max(dot(normal, -uLightDirection), 0.0);
  vec3 ambient = uColor.rgb * 0.4;
  vec3 diffuse = uColor.rgb * light * 0.6;
  vec3 finalColor = ambient + diffuse;

  // Fog calculation
  float depth = length(vPosition);
  float fogFactor = smoothstep(uFogNear, uFogFar, depth);
  finalColor = mix(finalColor, uFogColor, fogFactor);

  gl_FragColor = vec4(finalColor, uColor.a * uOpacity);
}
`;

export var LINE_VERTEX_SHADER = `
attribute vec3 aPosition;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
void main() {
  gl_Position = uProjectionMatrix * uModelViewMatrix * vec4(aPosition, 1.0);
}
`;

export var LINE_FRAGMENT_SHADER = `
precision mediump float;
uniform vec4 uColor;
uniform float uOpacity;
void main() {
  gl_FragColor = vec4(uColor.rgb, uColor.a * uOpacity);
}
`;

export var PARTICLE_VERTEX_SHADER = `
attribute vec3 aPosition;
attribute float aSize;
uniform mat4 uProjectionMatrix;
uniform mat4 uModelViewMatrix;
void main() {
  gl_Position = uProjectionMatrix * uModelViewMatrix * vec4(aPosition, 1.0);
  gl_PointSize = aSize;
}
`;

export var PARTICLE_FRAGMENT_SHADER = `
precision mediump float;
uniform vec4 uColor;
void main() {
  float dist = length(gl_PointCoord - vec2(0.5));
  if (dist > 0.5) discard;
  float alpha = 1.0 - smoothstep(0.2, 0.5, dist);
  gl_FragColor = vec4(uColor.rgb, uColor.a * alpha);
}
`;

// ============ MATH UTILITIES ============

export function mat4Create() {
  return new Float32Array([
    1,0,0,0,
    0,1,0,0,
    0,0,1,0,
    0,0,0,1
  ]);
}

export function mat4Perspective(out, fovy, aspect, near, far) {
  var f = 1.0 / Math.tan(fovy / 2);
  var nf = 1 / (near - far);
  out[0] = f / aspect; out[1] = 0; out[2] = 0; out[3] = 0;
  out[4] = 0; out[5] = f; out[6] = 0; out[7] = 0;
  out[8] = 0; out[9] = 0; out[10] = (far + near) * nf; out[11] = -1;
  out[12] = 0; out[13] = 0; out[14] = 2 * far * near * nf; out[15] = 0;
  return out;
}

export function mat4LookAt(out, eye, center, up) {
  var zx = eye[0] - center[0], zy = eye[1] - center[1], zz = eye[2] - center[2];
  var zlen = Math.sqrt(zx*zx + zy*zy + zz*zz);
  zx /= zlen; zy /= zlen; zz /= zlen;
  var xx = up[1]*zz - up[2]*zy, xy = up[2]*zx - up[0]*zz, xz = up[0]*zy - up[1]*zx;
  var xlen = Math.sqrt(xx*xx + xy*xy + xz*xz);
  xx /= xlen; xy /= xlen; xz /= xlen;
  var yx = zy*xz - zz*xy, yy = zz*xx - zx*xz, yz = zx*xy - zy*xx;
  out[0] = xx; out[1] = xy; out[2] = xz; out[3] = 0;
  out[4] = yx; out[5] = yy; out[6] = yz; out[7] = 0;
  out[8] = zx; out[9] = zy; out[10] = zz; out[11] = 0;
  out[12] = -(xx*eye[0] + xy*eye[1] + xz*eye[2]);
  out[13] = -(yx*eye[0] + yy*eye[1] + yz*eye[2]);
  out[14] = -(zx*eye[0] + zy*eye[1] + zz*eye[2]);
  out[15] = 1;
  return out;
}

export function mat4Multiply(out, a, b) {
  for (var i = 0; i < 4; i++) {
    for (var j = 0; j < 4; j++) {
      out[i*4+j] = a[i*4]*b[j] + a[i*4+1]*b[4+j] + a[i*4+2]*b[8+j] + a[i*4+3]*b[12+j];
    }
  }
  return out;
}

export function mat4Invert(out, a) {
  var a00 = a[0], a01 = a[1], a02 = a[2], a03 = a[3];
  var a10 = a[4], a11 = a[5], a12 = a[6], a13 = a[7];
  var a20 = a[8], a21 = a[9], a22 = a[10], a23 = a[11];
  var a30 = a[12], a31 = a[13], a32 = a[14], a33 = a[15];
  var b00 = a00*a11 - a01*a10, b01 = a00*a12 - a02*a10, b02 = a00*a13 - a03*a10;
  var b03 = a01*a12 - a02*a11, b04 = a01*a13 - a03*a11, b05 = a02*a13 - a03*a12;
  var b06 = a20*a31 - a21*a30, b07 = a20*a32 - a22*a30, b08 = a20*a33 - a23*a30;
  var b09 = a21*a32 - a22*a31, b10 = a21*a33 - a23*a31, b11 = a22*a33 - a23*a32;
  var det = b00*b11 - b01*b10 + b02*b09 + b03*b08 - b04*b07 + b05*b06;
  if (!det) return null;
  det = 1.0 / det;
  out[0] = (a11*b11 - a12*b10 + a13*b09)*det; out[1] = (a02*b10 - a01*b11 - a03*b09)*det;
  out[2] = (a31*b05 - a32*b04 + a33*b03)*det; out[3] = (a22*b04 - a21*b05 - a23*b03)*det;
  out[4] = (a12*b08 - a10*b11 - a13*b07)*det; out[5] = (a00*b11 - a02*b08 + a03*b07)*det;
  out[6] = (a32*b02 - a30*b05 - a33*b01)*det; out[7] = (a20*b05 - a22*b02 + a23*b01)*det;
  out[8] = (a10*b10 - a11*b08 + a13*b06)*det; out[9] = (a01*b08 - a00*b10 - a03*b06)*det;
  out[10] = (a30*b04 - a31*b02 + a33*b00)*det; out[11] = (a21*b02 - a20*b04 - a23*b00)*det;
  out[12] = (a11*b07 - a10*b09 - a12*b06)*det; out[13] = (a00*b09 - a01*b07 + a02*b06)*det;
  out[14] = (a31*b01 - a30*b03 - a32*b00)*det; out[15] = (a20*b03 - a21*b01 + a22*b00)*det;
  return out;
}

export function mat4Transpose(out, a) {
  out[0] = a[0]; out[1] = a[4]; out[2] = a[8]; out[3] = a[12];
  out[4] = a[1]; out[5] = a[5]; out[6] = a[9]; out[7] = a[13];
  out[8] = a[2]; out[9] = a[6]; out[10] = a[10]; out[11] = a[14];
  out[12] = a[3]; out[13] = a[7]; out[14] = a[11]; out[15] = a[15];
  return out;
}

export function mat4FromTranslation(out, v) {
  out[0] = 1; out[1] = 0; out[2] = 0; out[3] = 0;
  out[4] = 0; out[5] = 1; out[6] = 0; out[7] = 0;
  out[8] = 0; out[9] = 0; out[10] = 1; out[11] = 0;
  out[12] = v[0]; out[13] = v[1]; out[14] = v[2]; out[15] = 1;
  return out;
}

export function mat4FromScaling(out, v) {
  out[0] = v[0]; out[1] = 0; out[2] = 0; out[3] = 0;
  out[4] = 0; out[5] = v[1]; out[6] = 0; out[7] = 0;
  out[8] = 0; out[9] = 0; out[10] = v[2]; out[11] = 0;
  out[12] = 0; out[13] = 0; out[14] = 0; out[15] = 1;
  return out;
}

export function mat4Identity(out) {
  out[0] = 1; out[1] = 0; out[2] = 0; out[3] = 0;
  out[4] = 0; out[5] = 1; out[6] = 0; out[7] = 0;
  out[8] = 0; out[9] = 0; out[10] = 1; out[11] = 0;
  out[12] = 0; out[13] = 0; out[14] = 0; out[15] = 1;
  return out;
}

// ============ GEOMETRY UTILITIES ============

export function createIcosahedron(radius) {
  radius = radius || 1;
  var phi = (1 + Math.sqrt(5)) / 2;
  var vertices = [
    [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
    [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
    [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1]
  ];
  var faces = [
    [0,11,5], [0,5,1], [0,1,7], [0,7,10], [0,10,11],
    [1,5,9], [5,11,4], [11,10,2], [10,7,6], [7,1,8],
    [3,9,4], [3,4,2], [3,2,6], [3,6,8], [3,8,9],
    [4,9,5], [2,4,11], [6,2,10], [8,6,7], [9,8,1]
  ];
  var positions = [];
  var normals = [];
  faces.forEach(function(f) {
    var v0 = vertices[f[0]], v1 = vertices[f[1]], v2 = vertices[f[2]];
    var nx = v0[0]+v1[0]+v2[0], ny = v0[1]+v1[1]+v2[1], nz = v0[2]+v1[2]+v2[2];
    var nlen = Math.sqrt(nx*nx + ny*ny + nz*nz);
    nx /= nlen; ny /= nlen; nz /= nlen;
    [v0, v1, v2].forEach(function(v) {
      var len = Math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
      positions.push(v[0]/len*radius, v[1]/len*radius, v[2]/len*radius);
      normals.push(nx, ny, nz);
    });
  });
  return { positions: new Float32Array(positions), normals: new Float32Array(normals), count: faces.length * 3 };
}

export function createLowPolySphere(radius, subdivisions) {
  subdivisions = subdivisions || 0;
  var geo = createIcosahedron(radius);
  if (subdivisions === 0) return geo;
  // Simplified: just return icosahedron for performance
  return geo;
}

export function degToRad(d) {
  return d * Math.PI / 180;
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

export function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}
