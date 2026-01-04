/**
 * ModelViewer - Inline 3D model viewer for Fabrication Console
 *
 * Displays the selected artifact in a side panel. Supports:
 * - GLB files via @google/model-viewer
 * - STL/3MF files via Three.js
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import '@google/model-viewer';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js';
import { Artifact, translateArtifactPath } from '../hooks/useFabricationWorkflow';
import './ModelViewer.css';

// Declare the model-viewer custom element for TypeScript
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          alt?: string;
          'auto-rotate'?: boolean;
          'camera-controls'?: boolean;
          'shadow-intensity'?: string;
          exposure?: string;
          poster?: string;
          loading?: 'auto' | 'lazy' | 'eager';
        },
        HTMLElement
      >;
    }
  }
}

interface ModelViewerProps {
  artifact: Artifact | null;
  isGenerating?: boolean;
}

export function ModelViewer({ artifact, isGenerating = false }: ModelViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationFrameRef = useRef<number | null>(null);
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
    cameraRef.current = null;
  }, []);

  // Initialize Three.js scene for STL/3MF
  const initThreeJS = useCallback(
    (container: HTMLDivElement, url: string, fileType: string) => {
      setLoading(true);
      setError(null);

      // Cleanup any existing scene
      cleanupThreeJS();

      const width = container.clientWidth;
      const height = container.clientHeight;

      // Scene
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x1a1a1a);
      sceneRef.current = scene;

      // Camera
      const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);
      camera.position.set(100, 100, 100);
      cameraRef.current = camera;

      // Renderer
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(window.devicePixelRatio);
      container.appendChild(renderer.domElement);
      rendererRef.current = renderer;

      // Controls
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 2;
      controlsRef.current = controls;

      // Lighting
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      scene.add(ambientLight);

      const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight1.position.set(1, 1, 1);
      scene.add(directionalLight1);

      const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
      directionalLight2.position.set(-1, -1, -1);
      scene.add(directionalLight2);

      // Grid helper
      const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x333333);
      scene.add(gridHelper);

      // Load model based on type
      const loadModel = () => {
        if (fileType === 'stl') {
          const loader = new STLLoader();
          loader.load(
            url,
            (geometry) => {
              const material = new THREE.MeshPhongMaterial({
                color: 0x7c5cff,
                specular: 0x111111,
                shininess: 100,
              });
              const mesh = new THREE.Mesh(geometry, material);

              // Center and scale the model
              geometry.computeBoundingBox();
              const box = geometry.boundingBox!;
              const center = new THREE.Vector3();
              box.getCenter(center);
              mesh.position.sub(center);

              const size = new THREE.Vector3();
              box.getSize(size);
              const maxDim = Math.max(size.x, size.y, size.z);
              const scale = 80 / maxDim;
              mesh.scale.setScalar(scale);

              scene.add(mesh);
              setLoading(false);
            },
            undefined,
            (err) => {
              console.error('STL load error:', err);
              setError('Failed to load STL file');
              setLoading(false);
            }
          );
        } else if (fileType === '3mf') {
          const loader = new ThreeMFLoader();
          loader.load(
            url,
            (object) => {
              // 3MF returns a Group
              const box = new THREE.Box3().setFromObject(object);
              const center = new THREE.Vector3();
              box.getCenter(center);
              object.position.sub(center);

              const size = new THREE.Vector3();
              box.getSize(size);
              const maxDim = Math.max(size.x, size.y, size.z);
              const scale = 80 / maxDim;
              object.scale.setScalar(scale);

              // Apply default material if none exists
              object.traverse((child) => {
                if (child instanceof THREE.Mesh && !child.material) {
                  child.material = new THREE.MeshPhongMaterial({
                    color: 0x10b981,
                    specular: 0x111111,
                    shininess: 100,
                  });
                }
              });

              scene.add(object);
              setLoading(false);
            },
            undefined,
            (err) => {
              console.error('3MF load error:', err);
              setError('Failed to load 3MF file');
              setLoading(false);
            }
          );
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
        const newHeight = container.clientHeight;
        camera.aspect = newWidth / newHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(newWidth, newHeight);
      };

      const resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(container);

      return () => {
        resizeObserver.disconnect();
        cleanupThreeJS();
      };
    },
    [cleanupThreeJS]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupThreeJS();
    };
  }, [cleanupThreeJS]);

  // Initialize Three.js when artifact changes (for STL/3MF)
  useEffect(() => {
    if (!artifact || !containerRef.current) return;

    const fileType = artifact.artifactType.toLowerCase();
    if (fileType === 'stl' || fileType === '3mf') {
      // Get the appropriate URL
      let url: string;
      if (fileType === 'stl' && artifact.metadata?.stl_location) {
        url = translateArtifactPath(artifact.metadata.stl_location);
      } else if (fileType === '3mf') {
        url = translateArtifactPath(artifact.location);
      } else {
        url = translateArtifactPath(artifact.location);
      }

      const cleanup = initThreeJS(containerRef.current, url, fileType);
      return cleanup;
    }
  }, [artifact, initThreeJS]);

  // Determine what to render
  const fileType = artifact?.artifactType.toLowerCase() || '';
  const useModelViewer = fileType === 'glb';
  const useThreeJS = fileType === 'stl' || fileType === '3mf';

  // Get GLB URL for model-viewer
  const getGlbUrl = () => {
    if (!artifact) return '';
    if (artifact.metadata?.glb_location) {
      return translateArtifactPath(artifact.metadata.glb_location);
    }
    if (fileType === 'glb') {
      return translateArtifactPath(artifact.location);
    }
    return '';
  };

  // Get thumbnail URL
  const thumbnailUrl = artifact?.metadata?.thumbnail || null;

  return (
    <div className="model-viewer">
      <div className="model-viewer__header">
        <h3 className="model-viewer__title">Model Preview</h3>
        {artifact && (
          <span className="model-viewer__type">{artifact.artifactType.toUpperCase()}</span>
        )}
      </div>

      <div className="model-viewer__canvas">
        {/* Empty state */}
        {!artifact && !isGenerating && (
          <div className="model-viewer__empty">
            <svg viewBox="0 0 24 24" className="model-viewer__empty-icon">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p>Generate or import a model to preview</p>
          </div>
        )}

        {/* Generating state */}
        {isGenerating && (
          <div className="model-viewer__generating">
            <div className="model-viewer__spinner" />
            <p>Generating 3D model...</p>
            <span className="model-viewer__hint">This may take a few minutes</span>
          </div>
        )}

        {/* GLB via model-viewer */}
        {artifact && useModelViewer && !isGenerating && (
          <model-viewer
            src={getGlbUrl()}
            alt={`3D preview of generated model`}
            auto-rotate
            camera-controls
            shadow-intensity="1"
            exposure="0.5"
            loading="eager"
            poster={thumbnailUrl || undefined}
            style={{ width: '100%', height: '100%', backgroundColor: '#1a1a1a' }}
          />
        )}

        {/* STL/3MF via Three.js */}
        {artifact && useThreeJS && !isGenerating && (
          <div ref={containerRef} className="model-viewer__threejs">
            {loading && (
              <div className="model-viewer__loading">
                <div className="model-viewer__spinner" />
                <p>Loading model...</p>
              </div>
            )}
            {error && (
              <div className="model-viewer__error">
                <p>{error}</p>
              </div>
            )}
          </div>
        )}

        {/* Unsupported type */}
        {artifact && !useModelViewer && !useThreeJS && !isGenerating && (
          <div className="model-viewer__unsupported">
            <p>Preview not available for {artifact.artifactType.toUpperCase()}</p>
            {thumbnailUrl && (
              <img src={thumbnailUrl} alt="Model thumbnail" className="model-viewer__thumbnail" />
            )}
          </div>
        )}
      </div>

      {/* Controls hint */}
      {artifact && !isGenerating && (
        <div className="model-viewer__controls">
          <span>Drag to rotate</span>
          <span>Scroll to zoom</span>
        </div>
      )}
    </div>
  );
}

export default ModelViewer;
