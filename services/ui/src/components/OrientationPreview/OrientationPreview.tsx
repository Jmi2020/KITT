/**
 * OrientationPreview - 3D preview with rotation matrix visualization
 *
 * Displays a mesh with applied rotation matrix, showing:
 * - Build plate grid with axis indicators
 * - Overhang highlighting (red for steep angles)
 * - Support for STL, GLB, and 3MF files
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js';
import './OrientationPreview.css';

export interface OrientationPreviewProps {
  /** URL to the mesh file (STL, GLB, 3MF) */
  meshUrl: string;
  /** File type (stl, glb, 3mf) */
  fileType: string;
  /** 3x3 rotation matrix to apply */
  rotationMatrix?: number[][];
  /** Overhang ratio (0-1) for display */
  overhangRatio?: number;
  /** Whether to highlight overhangs */
  showOverhangs?: boolean;
  /** Build plate dimensions [X, Y, Z] in mm */
  buildPlate?: [number, number, number];
  /** Callback when mesh is loaded */
  onMeshLoaded?: (dimensions: [number, number, number]) => void;
  /** Container height in pixels */
  height?: number;
  /** Whether to auto-rotate */
  autoRotate?: boolean;
}

// Default identity matrix
const IDENTITY_MATRIX: number[][] = [
  [1, 0, 0],
  [0, 1, 0],
  [0, 0, 1],
];

export function OrientationPreview({
  meshUrl,
  fileType,
  rotationMatrix = IDENTITY_MATRIX,
  overhangRatio,
  showOverhangs = false,
  buildPlate = [200, 200, 200],
  onMeshLoaded,
  height = 300,
  autoRotate = false,
}: OrientationPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const meshRef = useRef<THREE.Object3D | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cleanup Three.js resources
  const cleanupThreeJS = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    if (controlsRef.current) {
      controlsRef.current.dispose();
      controlsRef.current = null;
    }
    if (rendererRef.current) {
      rendererRef.current.dispose();
      rendererRef.current.domElement.remove();
      rendererRef.current = null;
    }
    if (sceneRef.current) {
      sceneRef.current.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          if (object.material instanceof THREE.Material) {
            object.material.dispose();
          } else if (Array.isArray(object.material)) {
            object.material.forEach((m) => m.dispose());
          }
        }
      });
      sceneRef.current = null;
    }
    meshRef.current = null;
    cameraRef.current = null;
  }, []);

  // Apply rotation matrix to mesh
  const applyRotationMatrix = useCallback((mesh: THREE.Object3D, matrix: number[][]) => {
    const transform = new THREE.Matrix4();
    transform.set(
      matrix[0][0], matrix[0][1], matrix[0][2], 0,
      matrix[1][0], matrix[1][1], matrix[1][2], 0,
      matrix[2][0], matrix[2][1], matrix[2][2], 0,
      0, 0, 0, 1
    );
    mesh.applyMatrix4(transform);
  }, []);

  // Initialize Three.js scene
  const initThreeJS = useCallback(() => {
    if (!containerRef.current) return;

    setLoading(true);
    setError(null);
    cleanupThreeJS();

    const container = containerRef.current;
    const width = container.clientWidth;
    const containerHeight = height;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / containerHeight, 0.1, 2000);
    camera.position.set(150, 150, 150);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, containerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 1;
    controlsRef.current = controls;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight1.position.set(1, 1, 1);
    scene.add(directionalLight1);

    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
    directionalLight2.position.set(-1, -1, -1);
    scene.add(directionalLight2);

    // Build plate (grid)
    const gridScale = Math.max(buildPlate[0], buildPlate[1]) / 200;
    const gridHelper = new THREE.GridHelper(
      Math.max(buildPlate[0], buildPlate[1]),
      20,
      0x444466,
      0x333355
    );
    scene.add(gridHelper);

    // Axis helper
    const axisHelper = new THREE.AxesHelper(50 * gridScale);
    scene.add(axisHelper);

    // Build volume outline (optional wireframe box)
    const volumeGeometry = new THREE.BoxGeometry(
      buildPlate[0],
      buildPlate[2],
      buildPlate[1]
    );
    const volumeEdges = new THREE.EdgesGeometry(volumeGeometry);
    const volumeLines = new THREE.LineSegments(
      volumeEdges,
      new THREE.LineBasicMaterial({ color: 0x4444ff, transparent: true, opacity: 0.3 })
    );
    volumeLines.position.y = buildPlate[2] / 2;
    scene.add(volumeLines);

    // Load model based on type
    const loadModel = () => {
      const type = fileType.toLowerCase();

      if (type === 'stl') {
        const loader = new STLLoader();
        loader.load(
          meshUrl,
          (geometry) => {
            // Choose color based on overhang ratio
            let meshColor = 0x7c5cff; // Purple (default)
            if (showOverhangs && overhangRatio !== undefined) {
              if (overhangRatio < 0.1) {
                meshColor = 0x10b981; // Green (minimal overhangs)
              } else if (overhangRatio < 0.3) {
                meshColor = 0xf59e0b; // Amber (moderate)
              } else {
                meshColor = 0xef4444; // Red (significant)
              }
            }

            const material = new THREE.MeshPhongMaterial({
              color: meshColor,
              specular: 0x222222,
              shininess: 80,
            });
            const mesh = new THREE.Mesh(geometry, material);

            // Apply rotation matrix
            applyRotationMatrix(mesh, rotationMatrix);

            // Center on grid
            geometry.computeBoundingBox();
            const box = geometry.boundingBox!;
            const center = new THREE.Vector3();
            box.getCenter(center);
            mesh.position.sub(center);

            // Get dimensions after rotation
            const size = new THREE.Vector3();
            box.getSize(size);

            // Place on build plate
            mesh.position.y = size.y / 2;

            // Scale to fit view
            const maxDim = Math.max(size.x, size.y, size.z);
            const targetScale = Math.min(buildPlate[0], buildPlate[1], buildPlate[2]) * 0.6;
            const scale = targetScale / maxDim;
            mesh.scale.setScalar(scale);
            mesh.position.y = (size.y * scale) / 2;

            scene.add(mesh);
            meshRef.current = mesh;

            // Report dimensions
            if (onMeshLoaded) {
              onMeshLoaded([size.x, size.y, size.z]);
            }

            setLoading(false);
          },
          undefined,
          (err) => {
            console.error('STL load error:', err);
            setError('Failed to load STL file');
            setLoading(false);
          }
        );
      } else if (type === '3mf') {
        const loader = new ThreeMFLoader();
        loader.load(
          meshUrl,
          (object) => {
            // Apply rotation matrix
            applyRotationMatrix(object, rotationMatrix);

            // Center and scale
            const box = new THREE.Box3().setFromObject(object);
            const center = new THREE.Vector3();
            box.getCenter(center);
            object.position.sub(center);

            const size = new THREE.Vector3();
            box.getSize(size);

            // Apply color based on overhangs
            if (showOverhangs && overhangRatio !== undefined) {
              let meshColor = 0x7c5cff;
              if (overhangRatio < 0.1) {
                meshColor = 0x10b981;
              } else if (overhangRatio < 0.3) {
                meshColor = 0xf59e0b;
              } else {
                meshColor = 0xef4444;
              }

              object.traverse((child) => {
                if (child instanceof THREE.Mesh) {
                  child.material = new THREE.MeshPhongMaterial({
                    color: meshColor,
                    specular: 0x222222,
                    shininess: 80,
                  });
                }
              });
            }

            // Scale to fit
            const maxDim = Math.max(size.x, size.y, size.z);
            const targetScale = Math.min(buildPlate[0], buildPlate[1], buildPlate[2]) * 0.6;
            const scale = targetScale / maxDim;
            object.scale.setScalar(scale);
            object.position.y = (size.y * scale) / 2;

            scene.add(object);
            meshRef.current = object;

            if (onMeshLoaded) {
              onMeshLoaded([size.x, size.y, size.z]);
            }

            setLoading(false);
          },
          undefined,
          (err) => {
            console.error('3MF load error:', err);
            setError('Failed to load 3MF file');
            setLoading(false);
          }
        );
      } else {
        setError(`${type.toUpperCase()} files cannot be used for orientation analysis. Please select an STL or 3MF file.`);
        setLoading(false);
      }
    };

    loadModel();

    // Animation loop
    const animate = () => {
      animationFrameRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Handle resize
    const handleResize = () => {
      if (!container || !renderer || !camera) return;
      const newWidth = container.clientWidth;
      camera.aspect = newWidth / containerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, containerHeight);
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      cleanupThreeJS();
    };
  }, [meshUrl, fileType, rotationMatrix, overhangRatio, showOverhangs, buildPlate, height, autoRotate, onMeshLoaded, cleanupThreeJS, applyRotationMatrix]);

  // Initialize on mount and when URL/rotation changes
  useEffect(() => {
    const cleanup = initThreeJS();
    return cleanup;
  }, [initThreeJS]);

  return (
    <div className="orientation-preview" style={{ height: `${height}px` }}>
      <div ref={containerRef} className="orientation-preview__canvas">
        {loading && (
          <div className="orientation-preview__loading">
            <div className="orientation-preview__spinner"></div>
            <p>Loading mesh...</p>
          </div>
        )}
        {error && (
          <div className="orientation-preview__error">
            <p>{error}</p>
          </div>
        )}
      </div>
      {overhangRatio !== undefined && (
        <div className="orientation-preview__overhang-indicator">
          <span className="orientation-preview__overhang-label">Overhangs:</span>
          <span
            className={`orientation-preview__overhang-value ${
              overhangRatio < 0.1
                ? 'orientation-preview__overhang-value--good'
                : overhangRatio < 0.3
                ? 'orientation-preview__overhang-value--moderate'
                : 'orientation-preview__overhang-value--significant'
            }`}
          >
            {(overhangRatio * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  );
}

export default OrientationPreview;
