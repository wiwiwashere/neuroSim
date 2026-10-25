"use client";

import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useQuery } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Color, type Mesh, type MeshStandardMaterial } from "three";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { api } from "@/lib/api";
import type { DegenerationFrame, GraphNode, SimulationResult, Subgraph } from "@/lib/types";
import { useChartColors } from "@/lib/theme";
import { cn } from "@/lib/utils";

const HEALTHY = "#e8e4de";
const IMPACT = "#6b1212";
const HOP_MAX = 3;
const PLAYBACK_FPS = 6;

type LaidOut = GraphNode & { px: number; py: number; pz: number; perHop: number[] };

function layoutNodes(nodes: GraphNode[], perHop: Map<string, number[]>): LaidOut[] {
  const groups = [...new Set(nodes.map((n) => n.group))];
  const xs = nodes.map((n) => n.x ?? 0);
  const ys = nodes.map((n) => n.y ?? 0);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(Math.max(...xs) - minX, 1);
  const spanY = Math.max(Math.max(...ys) - minY, 1);
  const scale = 14 / Math.max(spanX, spanY);
  return nodes.map((n) => ({
    ...n,
    px: ((n.x ?? 0) - minX - spanX / 2) * scale,
    py: -((n.y ?? 0) - minY - spanY / 2) * scale,
    pz: (groups.indexOf(n.group) - (groups.length - 1) / 2) * 3.4,
    perHop: perHop.get(n.id) ?? [],
  }));
}

function mergePerHop(graph: Subgraph, result: SimulationResult): Map<string, number[]> {
  const byRoot = new Map(result.top_neurons.map((n) => [String(n.root_id), n.per_hop]));
  const byType = new Map<string, number[]>();
  for (const n of result.top_neurons) {
    if (n.cell_type) byType.set(n.cell_type, n.per_hop);
  }
  const out = new Map<string, number[]>();
  for (const node of graph.nodes) {
    out.set(node.id, byRoot.get(node.id) ?? byType.get(node.label) ?? []);
  }
  return out;
}

function lerpHex(a: string, b: string, t: number): string {
  const c = new Color(a).lerp(new Color(b), Math.min(1, Math.max(0, t)));
  return `#${c.getHexString()}`;
}

function hopImpact(node: LaidOut, t: number): number {
  if (t <= 0) return 0;
  const keys = [0, ...(node.perHop.length ? node.perHop : [node.impact])];
  while (keys.length <= HOP_MAX) keys.push(keys[keys.length - 1] ?? node.impact);
  const capped = Math.min(t, HOP_MAX);
  const i = Math.min(HOP_MAX, Math.max(0, Math.floor(capped)));
  const j = Math.min(HOP_MAX, i + 1);
  const frac = capped - i;
  return keys[i]! + (keys[j]! - keys[i]!) * Math.min(1, Math.max(0, frac));
}

function colorAt(node: LaidOut, t: number, frame: DegenerationFrame | null, seed: string): string {
  if (frame) {
    if (node.is_seed) return lerpHex(HEALTHY, seed, 1 - frame.seed_health);
    const activity = frame.region_activity[node.group];
    const dim = activity == null ? node.impact * (1 - frame.seed_health) : 1 - activity;
    return lerpHex(HEALTHY, IMPACT, dim);
  }
  if (node.is_seed) return t > 0 ? seed : HEALTHY;
  return lerpHex(HEALTHY, IMPACT, hopImpact(node, t));
}

export function Network3D({
  graph,
  aboveChance,
  result,
  selectedId,
  onSelect,
}: {
  graph: Subgraph;
  aboveChance: Set<string>;
  result: SimulationResult;
  selectedId?: string | null;
  onSelect?: (node: GraphNode) => void;
}) {
  const c = useChartColors();
  const dynamics = useQuery({
    queryKey: ["dynamics", result.run_id],
    queryFn: () => api.dynamics(result.run_id),
    enabled: !!result.run_id,
  });
  const frames = dynamics.data?.frames ?? [];
  const maxTick = frames.length > 0 ? frames.length - 1 : HOP_MAX;
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    setTick(0);
  }, [result.run_id, frames.length]);

  useEffect(() => {
    if (!playing) return;
    const ms = 1000 / (PLAYBACK_FPS * speed);
    const id = window.setInterval(() => {
      setTick((t) => (t >= maxTick ? 0 : t + 1));
    }, ms);
    return () => window.clearInterval(id);
  }, [playing, speed, maxTick]);

  const laid = useMemo(() => layoutNodes(graph.nodes, mergePerHop(graph, result)), [graph, result]);
  const pos = useMemo(() => new Map(laid.map((n) => [n.id, n])), [laid]);
  const frame = frames.length ? (frames[Math.min(tick, frames.length - 1)] ?? null) : null;
  const tHop = frames.length ? (tick / Math.max(maxTick, 1)) * HOP_MAX : tick;
  const health = frame?.seed_health ?? 1 - tick / Math.max(maxTick, 1);
  const seed = c?.seed ?? "#eb6834";
  const signal = c?.signal ?? "#3b6fd8";
  const faint = c?.faint ?? "#9a9389";
  const border = c?.border ?? "#d9d2c8";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="relative min-h-0 flex-1">
        <Canvas camera={{ position: [0, 6, 18], fov: 45 }} dpr={[1, 2]} gl={{ antialias: true }}>
          <color attach="background" args={["#0e0d0c"]} />
          <ambientLight intensity={0.55} />
          <pointLight position={[8, 12, 10]} intensity={1.1} />
          <pointLight position={[-10, -4, -6]} intensity={0.35} color={seed} />
          <Scene
            laid={laid}
            graph={graph}
            pos={pos}
            tHop={tHop}
            frame={frame}
            seed={seed}
            signal={signal}
            faint={faint}
            border={border}
            aboveChance={aboveChance}
            selectedId={selectedId ?? null}
            onSelect={onSelect}
          />
          <OrbitControls enablePan makeDefault minDistance={6} maxDistance={48} />
          <EffectComposer>
            <Bloom luminanceThreshold={0.45} intensity={0.85} mipmapBlur />
          </EffectComposer>
        </Canvas>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t px-3 py-2.5">
        <Button type="button" size="sm" variant="outline" onClick={() => setPlaying((p) => !p)}>
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          {playing ? "Pause" : "Replay"}
        </Button>
        <div className="min-w-[12rem] flex-1">
          <Slider
            min={0}
            max={maxTick}
            step={1}
            value={[Math.min(tick, maxTick)]}
            onValueChange={(v) => {
              setPlaying(false);
              setTick(v[0] ?? 0);
            }}
          />
        </div>
        <span className="w-24 font-mono text-[11px] text-muted-foreground tabular">
          {frame ? `t=${frame.t.toFixed(1)}s` : `hop ${tick}/${HOP_MAX}`}
        </span>
        <label className="flex items-center gap-2 text-[11.5px] text-muted-foreground">
          Speed
          <span className="w-28">
            <Slider min={0.25} max={3} step={0.25} value={[speed]} onValueChange={(v) => setSpeed(v[0] ?? 1)} />
          </span>
          <span className="w-8 font-mono tabular">{speed}×</span>
        </label>
        <span className="text-[11px] text-muted-foreground">seed health {Math.round(health * 100)}%</span>
      </div>
    </div>
  );
}

function Scene({
  laid,
  graph,
  pos,
  tHop,
  frame,
  seed,
  signal,
  faint,
  border,
  aboveChance,
  selectedId,
  onSelect,
}: {
  laid: LaidOut[];
  graph: Subgraph;
  pos: Map<string, LaidOut>;
  tHop: number;
  frame: DegenerationFrame | null;
  seed: string;
  signal: string;
  faint: string;
  border: string;
  aboveChance: Set<string>;
  selectedId: string | null;
  onSelect?: (node: GraphNode) => void;
}) {
  const hulls = useMemo(() => {
    const by = new Map<string, LaidOut[]>();
    for (const n of laid) {
      const list = by.get(n.group) ?? [];
      list.push(n);
      by.set(n.group, list);
    }
    return [...by.entries()].map(([group, nodes]) => {
      const xs = nodes.map((n) => n.px);
      const ys = nodes.map((n) => n.py);
      const zs = nodes.map((n) => n.pz);
      const min = [Math.min(...xs), Math.min(...ys), Math.min(...zs)] as const;
      const max = [Math.max(...xs), Math.max(...ys), Math.max(...zs)] as const;
      return {
        group,
        cx: (min[0] + max[0]) / 2,
        cy: (min[1] + max[1]) / 2,
        cz: (min[2] + max[2]) / 2,
        sx: Math.max(max[0] - min[0], 0.8) + 1.6,
        sy: Math.max(max[1] - min[1], 0.8) + 1.6,
        sz: Math.max(max[2] - min[2], 0.6) + 1.2,
      };
    });
  }, [laid]);

  return (
    <group>
      {hulls.map((h) => {
        const hit = aboveChance.has(h.group);
        return (
          <mesh key={h.group} position={[h.cx, h.cy, h.cz]}>
            <boxGeometry args={[h.sx, h.sy, h.sz]} />
            <meshBasicMaterial color={hit ? signal : border} transparent opacity={hit ? 0.14 : 0.06} depthWrite={false} />
          </mesh>
        );
      })}
      {graph.edges.map((e, i) => {
        const a = pos.get(e.source);
        const b = pos.get(e.target);
        if (!a || !b) return null;
        return (
          <Line
            key={i}
            points={[
              [a.px, a.py, a.pz],
              [b.px, b.py, b.pz],
            ]}
            color={faint}
            lineWidth={1.2}
            transparent
            opacity={Math.max(0.12, Math.min(0.7, e.weight))}
            dashed={e.lost > 0}
            dashSize={0.18}
            gapSize={0.1}
          />
        );
      })}
      {laid.map((n) => (
        <NeuronMesh
          key={n.id}
          node={n}
          color={colorAt(n, tHop, frame, seed)}
          selected={selectedId === n.id}
          signal={signal}
          seed={seed}
          activity={frame?.region_activity[n.group] ?? 1 - hopImpact(n, tHop)}
          onSelect={onSelect}
        />
      ))}
    </group>
  );
}

function NeuronMesh({
  node,
  color,
  selected,
  signal,
  seed,
  activity,
  onSelect,
}: {
  node: LaidOut;
  color: string;
  selected: boolean;
  signal: string;
  seed: string;
  activity: number;
  onSelect?: (node: GraphNode) => void;
}) {
  const ref = useRef<Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const target = useRef(new Color(color));
  target.current.set(color);

  useFrame(({ clock }) => {
    const mesh = ref.current;
    if (!mesh) return;
    const mat = mesh.material as MeshStandardMaterial;
    mat.color.lerp(target.current, 0.12);
    const pulse = 1 + 0.1 * Math.max(0, activity) * Math.sin(clock.elapsedTime * 3.2 + node.px);
    mesh.scale.setScalar(pulse);
    if (node.is_seed) mat.emissive.lerp(new Color(seed), 0.15);
  });

  return (
    <group
      position={[node.px, node.py, node.pz]}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect?.(node);
      }}
    >
      <mesh ref={ref}>
        <sphereGeometry args={[node.is_seed ? 0.8 : 0.4, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={node.is_seed ? seed : color}
          emissiveIntensity={node.is_seed ? 0.85 : 0.12}
          roughness={0.45}
          metalness={0.08}
        />
      </mesh>
      {selected && (
        <mesh>
          <sphereGeometry args={[(node.is_seed ? 0.8 : 0.4) * 1.35, 16, 16]} />
          <meshBasicMaterial color={signal} wireframe transparent opacity={0.7} />
        </mesh>
      )}
      {hovered && (
        <Html center sprite style={{ pointerEvents: "none" }}>
          <div className={cn("min-w-[9rem] rounded-md border bg-card/95 px-2 py-1 text-[11px] leading-snug text-foreground shadow-md")}>
            <p className="font-medium">{node.label}</p>
            <p className="text-muted-foreground">{node.group}</p>
            <p className="font-mono tabular">{node.is_seed ? "seed" : `impact ${node.impact.toFixed(2)}`}</p>
          </div>
        </Html>
      )}
    </group>
  );
}
