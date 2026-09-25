import React, { useEffect, useRef } from "react";
import { VoiceState } from "./voiceTypes";

interface NanviNeuralCoreProps {
  state: VoiceState;
  audioLevel: number; // 0.0 - 1.0 real-time reactive volume
  className?: string;
  size?: number; // default 320px
}

interface Particle {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  radius: number;
  alpha: number;
  baseAlpha: number;
}

export const NanviNeuralCore: React.FC<NanviNeuralCoreProps> = ({
  state,
  audioLevel,
  className = "",
  size = 340,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number | null>(null);

  // Smooth interpolated properties
  const smoothedLevel = useRef(0);
  const rotationAngle = useRef({ x: 0.2, y: 0.4, z: 0 });
  const corePulse = useRef(1);
  const particlesRef = useRef<Particle[]>([]);
  const lastTimeRef = useRef(performance.now());

  // Initialize particulate field
  useEffect(() => {
    const count = 55;
    const particles: Particle[] = [];
    for (let i = 0; i < count; i++) {
      const radius = 60 + Math.random() * 85;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);

      particles.push({
        x: radius * Math.sin(phi) * Math.cos(theta),
        y: radius * Math.sin(phi) * Math.sin(theta),
        z: radius * Math.cos(phi),
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        vz: (Math.random() - 0.5) * 0.4,
        radius: 1.2 + Math.random() * 1.8,
        alpha: 0.2 + Math.random() * 0.6,
        baseAlpha: 0.2 + Math.random() * 0.6,
      });
    }
    particlesRef.current = particles;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const render = (time: number) => {
      const dt = Math.min((time - lastTimeRef.current) / 1000, 0.05);
      lastTimeRef.current = time;

      // 1. Smooth audio reactive level
      const targetLevel = state === "muted" ? 0 : audioLevel;
      const smoothingFactor = targetLevel > smoothedLevel.current ? 0.35 : 0.12;
      smoothedLevel.current += (targetLevel - smoothedLevel.current) * smoothingFactor;
      const level = smoothedLevel.current;

      // 2. State-dependent rotation & energy parameters
      let rotSpeedX = 0.25;
      let rotSpeedY = 0.35;
      let rotSpeedZ = 0.1;
      let coreTargetScale = 1.0;
      let ringGlowColor = "rgba(249, 115, 22, 0.75)";
      let coreColor = "#ea580c";
      let particleConvergence = 0;

      switch (state) {
        case "idle":
          rotSpeedX = 0.18;
          rotSpeedY = 0.24;
          rotSpeedZ = 0.08;
          coreTargetScale = 1.0 + 0.06 * Math.sin(time * 0.0018);
          ringGlowColor = "rgba(249, 115, 22, 0.55)";
          break;

        case "listening":
          // Responsive to mic volume
          rotSpeedX = 0.35 + level * 0.6;
          rotSpeedY = 0.45 + level * 0.8;
          rotSpeedZ = 0.15 + level * 0.3;
          coreTargetScale = 1.05 + level * 0.45 + 0.05 * Math.sin(time * 0.004);
          ringGlowColor = `rgba(249, 115, 22, ${0.7 + level * 0.3})`;
          coreColor = "#f97316";
          break;

        case "processing":
          // Internal intelligence layers spinning fast, particles drawn inwards
          rotSpeedX = 0.95;
          rotSpeedY = 1.25;
          rotSpeedZ = 0.5;
          coreTargetScale = 0.92 + 0.12 * Math.sin(time * 0.006);
          ringGlowColor = "rgba(251, 146, 60, 0.85)";
          coreColor = "#ea580c";
          particleConvergence = 1.6;
          break;

        case "speaking":
          // Assistant speaking amplitude response
          rotSpeedX = 0.3 + level * 0.5;
          rotSpeedY = 0.4 + level * 0.7;
          rotSpeedZ = 0.2 + level * 0.3;
          coreTargetScale = 1.08 + level * 0.38 + 0.06 * Math.sin(time * 0.005);
          ringGlowColor = `rgba(234, 88, 12, ${0.75 + level * 0.25})`;
          coreColor = "#f97316";
          break;

        case "interrupted":
          coreTargetScale = 0.88;
          rotSpeedX = 0.5;
          rotSpeedY = 0.6;
          ringGlowColor = "rgba(249, 115, 22, 0.6)";
          break;

        case "muted":
          rotSpeedX = 0.08;
          rotSpeedY = 0.1;
          rotSpeedZ = 0.04;
          coreTargetScale = 0.95;
          ringGlowColor = "rgba(148, 163, 184, 0.4)";
          coreColor = "#64748b";
          break;

        case "error":
          coreTargetScale = 0.95;
          ringGlowColor = "rgba(239, 68, 68, 0.6)";
          coreColor = "#dc2626";
          break;
      }

      if (prefersReducedMotion) {
        rotSpeedX *= 0.15;
        rotSpeedY *= 0.15;
        rotSpeedZ *= 0.1;
      }

      rotationAngle.current.x += rotSpeedX * dt;
      rotationAngle.current.y += rotSpeedY * dt;
      rotationAngle.current.z += rotSpeedZ * dt;
      corePulse.current += (coreTargetScale - corePulse.current) * 0.15;

      // Clear frame with transparent slate
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;

      // 3. Draw Ambient Radiant Aura / Background Glow
      const auraRadius = (size * 0.42) * corePulse.current;
      const auraGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, auraRadius);
      if (state === "muted") {
        auraGrad.addColorStop(0, "rgba(148, 163, 184, 0.18)");
        auraGrad.addColorStop(0.5, "rgba(148, 163, 184, 0.05)");
        auraGrad.addColorStop(1, "rgba(148, 163, 184, 0)");
      } else if (state === "error") {
        auraGrad.addColorStop(0, "rgba(239, 68, 68, 0.25)");
        auraGrad.addColorStop(0.6, "rgba(239, 68, 68, 0.06)");
        auraGrad.addColorStop(1, "rgba(239, 68, 68, 0)");
      } else {
        const intensity = 0.28 + level * 0.25;
        auraGrad.addColorStop(0, `rgba(249, 115, 22, ${intensity})`);
        auraGrad.addColorStop(0.4, `rgba(234, 88, 12, ${intensity * 0.5})`);
        auraGrad.addColorStop(0.75, `rgba(253, 186, 116, ${intensity * 0.15})`);
        auraGrad.addColorStop(1, "rgba(249, 115, 22, 0)");
      }
      ctx.fillStyle = auraGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, auraRadius, 0, Math.PI * 2);
      ctx.fill();

      // 3D Projection Helper
      const fov = 340;
      const project = (x: number, y: number, z: number) => {
        // Rotate around X
        const cosX = Math.cos(rotationAngle.current.x);
        const sinX = Math.sin(rotationAngle.current.x);
        const y1 = y * cosX - z * sinX;
        const z1 = y * sinX + z * cosX;

        // Rotate around Y
        const cosY = Math.cos(rotationAngle.current.y);
        const sinY = Math.sin(rotationAngle.current.y);
        const x2 = x * cosY + z1 * sinY;
        const z2 = -x * sinY + z1 * cosY;

        // Rotate around Z
        const cosZ = Math.cos(rotationAngle.current.z);
        const sinZ = Math.sin(rotationAngle.current.z);
        const x3 = x2 * cosZ - y1 * sinZ;
        const y3 = x2 * sinZ + y1 * cosZ;

        const distance = fov / (fov + z2 + 180);
        return {
          px: cx + x3 * distance,
          py: cy + y3 * distance,
          scale: distance,
          z: z2,
        };
      };

      // 4. Update and Draw Ambient Neural Particles
      const particles = particlesRef.current;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        if (particleConvergence > 0) {
          // In processing state, pull toward core
          p.x += (0 - p.x) * 0.03 * particleConvergence;
          p.y += (0 - p.y) * 0.03 * particleConvergence;
          p.z += (0 - p.z) * 0.03 * particleConvergence;
          if (Math.hypot(p.x, p.y, p.z) < 20) {
            // Respawn outward
            const rad = 75 + Math.random() * 40;
            const th = Math.random() * Math.PI * 2;
            p.x = rad * Math.cos(th);
            p.y = (Math.random() - 0.5) * 50;
            p.z = rad * Math.sin(th);
          }
        } else {
          p.x += p.vx;
          p.y += p.vy;
          p.z += p.vz;
          const dist = Math.hypot(p.x, p.y, p.z);
          if (dist > 120 || dist < 30) {
            p.vx *= -1;
            p.vy *= -1;
            p.vz *= -1;
          }
        }

        const proj = project(p.x, p.y, p.z);
        const alpha = Math.max(0.1, Math.min(1.0, p.baseAlpha * proj.scale * (1 + level * 0.5)));

        ctx.fillStyle =
          state === "muted"
            ? `rgba(148, 163, 184, ${alpha * 0.6})`
            : `rgba(253, 186, 116, ${alpha})`;
        ctx.beginPath();
        ctx.arc(proj.px, proj.py, p.radius * proj.scale, 0, Math.PI * 2);
        ctx.fill();
      }

      // 5. Draw Layered Translucent Geometric Orbital Rings (Outer Neural Fields)
      const ringConfigs = [
        { radius: 76 * corePulse.current, tilt: 0.45, segments: 64, width: 2.2, speedOffset: 1.0 },
        { radius: 98 * (1 + level * 0.18), tilt: -0.6, segments: 64, width: 1.8, speedOffset: -0.75 },
        { radius: 114 * (1 + level * 0.22), tilt: 0.85, segments: 64, width: 1.5, speedOffset: 0.5 },
      ];

      for (let rIdx = 0; rIdx < ringConfigs.length; rIdx++) {
        const rc = ringConfigs[rIdx];
        const points: Array<{ px: number; py: number; scale: number; z: number }> = [];

        for (let i = 0; i <= rc.segments; i++) {
          const theta = (i / rc.segments) * Math.PI * 2;
          const rx = rc.radius * Math.cos(theta);
          const ry = rc.radius * Math.sin(theta) * Math.cos(rc.tilt);
          const rz = rc.radius * Math.sin(theta) * Math.sin(rc.tilt);
          points.push(project(rx, ry, rz));
        }

        // Draw segmented ring with depth fade
        for (let i = 0; i < points.length - 1; i++) {
          const p1 = points[i];
          const p2 = points[i + 1];
          const avgZ = (p1.z + p2.z) / 2;
          const depthAlpha = Math.max(0.2, Math.min(0.9, (avgZ + 120) / 240));

          ctx.beginPath();
          ctx.moveTo(p1.px, p1.py);
          ctx.lineTo(p2.px, p2.py);
          ctx.strokeStyle = ringGlowColor.replace(/[\d\.]+\)$/, `${depthAlpha})`);
          ctx.lineWidth = rc.width * p1.scale;
          ctx.stroke();
        }

        // Orbital Data Nodes on rings
        const nodeAngle = time * 0.001 * rc.speedOffset;
        const nx = rc.radius * Math.cos(nodeAngle);
        const ny = rc.radius * Math.sin(nodeAngle) * Math.cos(rc.tilt);
        const nz = rc.radius * Math.sin(nodeAngle) * Math.sin(rc.tilt);
        const nodeProj = project(nx, ny, nz);

        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(nodeProj.px, nodeProj.py, 2.8 * nodeProj.scale, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = ringGlowColor;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(nodeProj.px, nodeProj.py, 5.5 * nodeProj.scale, 0, Math.PI * 2);
        ctx.stroke();
      }

      // 6. Draw Central Neural Core Object
      // Layered translucent sphere with crystalline refractive highlights
      const coreBaseRadius = 38 * corePulse.current;

      // Core back shadow
      const shadowGrad = ctx.createRadialGradient(
        cx + 3,
        cy + 4,
        coreBaseRadius * 0.2,
        cx,
        cy,
        coreBaseRadius * 1.3
      );
      shadowGrad.addColorStop(0, "rgba(0, 0, 0, 0.35)");
      shadowGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = shadowGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, coreBaseRadius * 1.3, 0, Math.PI * 2);
      ctx.fill();

      // Main inner radiant core
      const coreGrad = ctx.createRadialGradient(
        cx - coreBaseRadius * 0.35,
        cy - coreBaseRadius * 0.35,
        coreBaseRadius * 0.05,
        cx,
        cy,
        coreBaseRadius
      );

      if (state === "muted") {
        coreGrad.addColorStop(0, "#cbd5e1");
        coreGrad.addColorStop(0.4, "#94a3b8");
        coreGrad.addColorStop(0.85, "#475569");
        coreGrad.addColorStop(1, "#1e293b");
      } else if (state === "error") {
        coreGrad.addColorStop(0, "#fca5a5");
        coreGrad.addColorStop(0.4, "#ef4444");
        coreGrad.addColorStop(0.9, "#b91c1c");
        coreGrad.addColorStop(1, "#7f1d1d");
      } else {
        coreGrad.addColorStop(0, "#ffffff"); // Crisp pearl center
        coreGrad.addColorStop(0.18, "#ffedd5"); // Warm peach
        coreGrad.addColorStop(0.42, "#fb923c"); // Amber
        coreGrad.addColorStop(0.78, coreColor); // Refined orange
        coreGrad.addColorStop(1, "#9a3412"); // Deep amber shadow
      }

      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, coreBaseRadius, 0, Math.PI * 2);
      ctx.fill();

      // Translucent Glass Highlights (Swiss-inspired enterprise precision)
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, coreBaseRadius, 0, Math.PI * 2);
      ctx.clip();

      // Crescent light reflection
      const highlightGrad = ctx.createLinearGradient(
        cx - coreBaseRadius,
        cy - coreBaseRadius,
        cx + coreBaseRadius * 0.5,
        cy + coreBaseRadius * 0.5
      );
      highlightGrad.addColorStop(0, "rgba(255, 255, 255, 0.75)");
      highlightGrad.addColorStop(0.4, "rgba(255, 255, 255, 0.1)");
      highlightGrad.addColorStop(1, "rgba(255, 255, 255, 0)");

      ctx.fillStyle = highlightGrad;
      ctx.beginPath();
      ctx.ellipse(
        cx - coreBaseRadius * 0.35,
        cy - coreBaseRadius * 0.35,
        coreBaseRadius * 0.7,
        coreBaseRadius * 0.42,
        Math.PI / 4,
        0,
        Math.PI * 2
      );
      ctx.fill();

      // Secondary subtle rim light
      ctx.strokeStyle = "rgba(255, 255, 255, 0.55)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, coreBaseRadius - 1.5, Math.PI * 0.75, Math.PI * 1.5);
      ctx.stroke();

      ctx.restore();

      // Soft outer rim stroke
      ctx.strokeStyle = state === "muted" ? "rgba(148, 163, 184, 0.4)" : "rgba(255, 237, 213, 0.6)";
      ctx.lineWidth = 1.0;
      ctx.beginPath();
      ctx.arc(cx, cy, coreBaseRadius, 0, Math.PI * 2);
      ctx.stroke();

      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [state, size]);

  return (
    <div
      className={`nanvi-neural-core-container relative flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
      aria-label={`Nanvi AI Visualizer: ${state}`}
      role="img"
    >
      <canvas ref={canvasRef} className="nanvi-neural-core-canvas block" />
    </div>
  );
};
