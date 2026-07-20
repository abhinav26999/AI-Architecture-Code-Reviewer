"use client";

import React, { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

interface GraphMetrics {
  afferent_coupling: number;
  efferent_coupling: number;
  instability: number;
}

interface GraphNode {
  file_path: string;
  language: string;
  metrics: GraphMetrics;
}

interface GraphEdge {
  source: string;
  target: string;
}

interface DependencyGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  circularDependencies: string[][];
  onSelectNode: (node: { file_path: string; metrics: GraphMetrics } | null) => void;
}

export default function DependencyGraph({
  nodes,
  edges,
  circularDependencies,
  onSelectNode,
}: DependencyGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Flatten circular dependencies for fast lookup
    const cyclicFiles = new Set<string>();
    circularDependencies.forEach((cycle) => {
      cycle.forEach((file) => cyclicFiles.add(file));
    });

    // Format elements for Cytoscape.js
    const cyNodes = nodes.map((n) => {
      const isCyclic = cyclicFiles.has(n.file_path);
      const filename = n.file_path.split("/").pop() || n.file_path;
      return {
        data: {
          id: n.file_path,
          label: filename,
          fullPath: n.file_path,
          isCyclic,
          metrics: n.metrics,
        },
      };
    });

    const cyEdges = edges.map((e, index) => ({
      data: {
        id: `edge-${index}`,
        source: e.source,
        target: e.target,
      },
    }));

    // Initialize Cytoscape
    const cy = cytoscape({
      container: containerRef.current,
      elements: [...cyNodes, ...cyEdges],
      style: [
        {
          selector: "node",
          style: {
            content: "data(label)",
            "font-size": "11px",
            "font-family": "system-ui, sans-serif",
            color: "#ffffff",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "background-color": "#4f46e5", // Indigo base
            width: "32px",
            height: "32px",
            "border-width": "2px",
            "border-color": "#1e1b4b",
            "overlay-padding": "6px",
            "transition-property": "background-color, border-color, width, height",
            "transition-duration": 0.2,
          },
        },
        {
          selector: "node[isCyclic]",
          style: {
            "background-color": "#f97316", // Orange/red for circular dependency
            "border-color": "#ea580c",
            "border-width": "3px",
          },
        },
        {
          selector: "node:selected",
          style: {
            "background-color": "#10b981", // Emerald for selection
            "border-color": "#047857",
            "border-width": "3px",
            width: "38px",
            height: "38px",
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#475569", // Slate edge
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.8,
          },
        },
      ],
      layout: {
        name: "cose", // Force-directed layout
        idealEdgeLength: () => 100,
        nodeOverlap: 20,
        refresh: 20,
        fit: true,
        padding: 30,
        randomize: false,
        componentSpacing: 100,
        nodeRepulsion: () => 400000,
        edgeElasticity: () => 100,
        nestingFactor: 5,
        gravity: 80,
        numIter: 1000,
        initialTemp: 200,
        coolingFactor: 0.95,
        minTemp: 1.0,
      } as any,
    });

    cyRef.current = cy;

    // Node click handlers
    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      onSelectNode({
        file_path: node.data("fullPath"),
        metrics: node.data("metrics"),
      });
    });

    // Canvas click clears selection
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        onSelectNode(null);
      }
    });

    return () => {
      if (cyRef.current) {
        try {
          cyRef.current.stop();
          cyRef.current.removeAllListeners();
          cyRef.current.destroy();
        } catch (e) {
          // ignore cleanup errors on unmount
        }
        cyRef.current = null;
      }
    };
  }, [nodes, edges, circularDependencies, onSelectNode]);

  const triggerLayout = () => {
    if (cyRef.current) {
      cyRef.current.layout({ name: "cose", animate: true } as any).run();
    }
  };

  return (
    <div className="relative w-full h-[500px] border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950/60 backdrop-blur-md">
      <div ref={containerRef} className="w-full h-full" />
      <button
        onClick={triggerLayout}
        className="absolute bottom-4 right-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg transition duration-200"
      >
        Reorganize Layout
      </button>
    </div>
  );
}
