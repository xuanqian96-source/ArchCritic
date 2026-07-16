(() => {
  "use strict";

  function hexToRgb(hex) {
    const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
    if (!match) return [1, 1, 1];
    return [
      parseInt(match[1], 16) / 255,
      parseInt(match[2], 16) / 255,
      parseInt(match[3], 16) / 255
    ];
  }

  function originFlags(origin) {
    switch (origin) {
      case "top-left":
        return [1, 0];
      case "bottom-right":
        return [0, 1];
      case "bottom-left":
        return [1, 1];
      case "top-right":
      default:
        return [0, 0];
    }
  }

  function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(message || "Shader compile failed");
    }
    return shader;
  }

  function createProgram(gl, vertexSource, fragmentSource) {
    const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexSource);
    const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentSource);
    const program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    gl.deleteShader(vertexShader);
    gl.deleteShader(fragmentShader);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      const message = gl.getProgramInfoLog(program);
      gl.deleteProgram(program);
      throw new Error(message || "Program link failed");
    }
    return program;
  }

  function mountReactBitsSideRays(container, options = {}) {
    if (!container) return () => {};

    const settings = {
      speed: 2.2,
      rayColor1: "#6c4dff",
      rayColor2: "#171719",
      intensity: 1.65,
      spread: 1.9,
      origin: "top-right",
      tilt: -9,
      saturation: 1.1,
      blend: 0.7,
      falloff: 1.85,
      opacity: 0.82,
      ...options
    };

    const canvas = document.createElement("canvas");
    canvas.className = "side-rays-canvas";
    const gl = canvas.getContext("webgl", {
      alpha: true,
      antialias: true,
      premultipliedAlpha: false,
      preserveDrawingBuffer: false
    });

    if (!gl) return () => {};

    container.replaceChildren(canvas);

    const vertexSource = `
      attribute vec2 position;
      void main() {
        gl_Position = vec4(position, 0.0, 1.0);
      }
    `;

    const fragmentSource = `
      precision highp float;

      uniform float iTime;
      uniform vec2 iResolution;
      uniform float iSpeed;
      uniform vec3 iRayColor1;
      uniform vec3 iRayColor2;
      uniform float iIntensity;
      uniform float iSpread;
      uniform float iFlipX;
      uniform float iFlipY;
      uniform float iTilt;
      uniform float iSaturation;
      uniform float iBlend;
      uniform float iFalloff;
      uniform float iOpacity;

      float rayStrength(vec2 raySource, vec2 rayRefDirection, vec2 coord, float seedA, float seedB, float speed) {
        vec2 sourceToCoord = coord - raySource;
        float cosAngle = dot(normalize(sourceToCoord), rayRefDirection);
        return clamp(
          (0.45 + 0.15 * sin(cosAngle * seedA + iTime * speed)) +
          (0.3 + 0.2 * cos(-cosAngle * seedB + iTime * speed)),
          0.0, 1.0
        ) * clamp((iResolution.x - length(sourceToCoord)) / iResolution.x, 0.5, 1.0);
      }

      void main() {
        vec2 fragCoord = gl_FragCoord.xy;
        if (iFlipX > 0.5) fragCoord.x = iResolution.x - fragCoord.x;
        if (iFlipY > 0.5) fragCoord.y = iResolution.y - fragCoord.y;

        vec2 coord = vec2(fragCoord.x, iResolution.y - fragCoord.y);
        vec2 rayPos = vec2(iResolution.x * 1.1, -0.5 * iResolution.y);

        float tiltRad = iTilt * 3.14159265 / 180.0;
        float cs = cos(tiltRad);
        float sn = sin(tiltRad);
        vec2 rel = coord - rayPos;
        vec2 tiltedCoord = vec2(rel.x * cs - rel.y * sn, rel.x * sn + rel.y * cs) + rayPos;

        float halfSpread = iSpread * 0.275;
        vec2 rayRefDir1 = normalize(vec2(cos(0.785398 + halfSpread), sin(0.785398 + halfSpread)));
        vec2 rayRefDir2 = normalize(vec2(cos(0.785398 - halfSpread), sin(0.785398 - halfSpread)));

        vec4 rays1 = vec4(iRayColor1, 1.0) * rayStrength(rayPos, rayRefDir1, tiltedCoord, 36.2214, 21.11349, iSpeed);
        vec4 rays2 = vec4(iRayColor2, 1.0) * rayStrength(rayPos, rayRefDir2, tiltedCoord, 22.3991, 18.0234, iSpeed * 0.2);

        vec4 color = rays1 * (1.0 - iBlend) * 0.9 + rays2 * iBlend * 0.9;
        float distanceToLight = length(fragCoord.xy - vec2(rayPos.x, iResolution.y - rayPos.y)) / iResolution.y;
        float brightness = iIntensity * 0.4 / pow(max(distanceToLight, 0.001), iFalloff);
        color.rgb *= brightness;

        float gray = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        color.rgb = mix(vec3(gray), color.rgb, iSaturation);
        color.a = max(color.r, max(color.g, color.b)) * iOpacity;
        gl_FragColor = color;
      }
    `;

    const program = createProgram(gl, vertexSource, fragmentSource);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW
    );

    const position = gl.getAttribLocation(program, "position");
    const uniforms = {
      iTime: gl.getUniformLocation(program, "iTime"),
      iResolution: gl.getUniformLocation(program, "iResolution"),
      iSpeed: gl.getUniformLocation(program, "iSpeed"),
      iRayColor1: gl.getUniformLocation(program, "iRayColor1"),
      iRayColor2: gl.getUniformLocation(program, "iRayColor2"),
      iIntensity: gl.getUniformLocation(program, "iIntensity"),
      iSpread: gl.getUniformLocation(program, "iSpread"),
      iFlipX: gl.getUniformLocation(program, "iFlipX"),
      iFlipY: gl.getUniformLocation(program, "iFlipY"),
      iTilt: gl.getUniformLocation(program, "iTilt"),
      iSaturation: gl.getUniformLocation(program, "iSaturation"),
      iBlend: gl.getUniformLocation(program, "iBlend"),
      iFalloff: gl.getUniformLocation(program, "iFalloff"),
      iOpacity: gl.getUniformLocation(program, "iOpacity")
    };

    const color1 = hexToRgb(settings.rayColor1);
    const color2 = hexToRgb(settings.rayColor2);
    const flips = originFlags(settings.origin);
    let animationFrame = 0;
    let disposed = false;

    function resize() {
      const rect = container.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.floor(rect.width));
      const height = Math.max(1, Math.floor(rect.height));
      const bufferWidth = Math.floor(width * dpr);
      const bufferHeight = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      if (canvas.width !== bufferWidth || canvas.height !== bufferHeight) {
        canvas.width = bufferWidth;
        canvas.height = bufferHeight;
        gl.viewport(0, 0, bufferWidth, bufferHeight);
      }
    }

    function render(time) {
      if (disposed) return;
      resize();
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      gl.uniform1f(uniforms.iTime, time * 0.001);
      gl.uniform2f(uniforms.iResolution, canvas.width, canvas.height);
      gl.uniform1f(uniforms.iSpeed, settings.speed);
      gl.uniform3f(uniforms.iRayColor1, color1[0], color1[1], color1[2]);
      gl.uniform3f(uniforms.iRayColor2, color2[0], color2[1], color2[2]);
      gl.uniform1f(uniforms.iIntensity, settings.intensity);
      gl.uniform1f(uniforms.iSpread, settings.spread);
      gl.uniform1f(uniforms.iFlipX, flips[0]);
      gl.uniform1f(uniforms.iFlipY, flips[1]);
      gl.uniform1f(uniforms.iTilt, settings.tilt);
      gl.uniform1f(uniforms.iSaturation, settings.saturation);
      gl.uniform1f(uniforms.iBlend, settings.blend);
      gl.uniform1f(uniforms.iFalloff, settings.falloff);
      gl.uniform1f(uniforms.iOpacity, settings.opacity);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      animationFrame = requestAnimationFrame(render);
    }

    window.addEventListener("resize", resize);
    animationFrame = requestAnimationFrame(render);

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resize);
      try {
        gl.getExtension("WEBGL_lose_context")?.loseContext();
      } catch (error) {
        void error;
      }
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
    };
  }

  window.mountReactBitsSideRays = mountReactBitsSideRays;
})();
