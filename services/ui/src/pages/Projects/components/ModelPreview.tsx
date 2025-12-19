/**
 * ModelPreview - 3D model preview modal supporting GLB, STL, and 3MF
 *
 * Uses:
 * - @google/model-viewer for GLB files (best quality, auto-rotate)
 * - Three.js for STL and 3MF files
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import '@google/model-viewer';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js';
import { ThreeMFLoader } from 'three/examples/jsm/loaders/3MFLoader.js';
import type { UnifiedArtifact } from '../types';

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

interface ModelPreviewProps {
  artifact: UnifiedArtifact | null;
  onClose: () => void;
}

// Types that can be previewed
const PREVIEWABLE_TYPES = ['glb', 'stl', '3mf'];

export function ModelPreview({ artifact, onClose }: ModelPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Close on escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

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

      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        cleanupThreeJS();
      };
    },
    [cleanupThreeJS]
  );

  useEffect(() => {
    if (!artifact) return;

    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      cleanupThreeJS();
    };
  }, [artifact, handleKeyDown, cleanupThreeJS]);

  // Initialize Three.js when artifact changes (for STL/3MF)
  useEffect(() => {
    if (!artifact || !containerRef.current) return;

    const fileType = artifact.artifactType.toLowerCase();
    if (fileType === 'stl' || fileType === '3mf') {
      const cleanup = initThreeJS(containerRef.current, artifact.downloadUrl, fileType);
      return cleanup;
    }
  }, [artifact, initThreeJS]);

  if (!artifact) return null;

  const fileType = artifact.artifactType.toLowerCase();
  const isSupported = PREVIEWABLE_TYPES.includes(fileType);
  const useModelViewer = fileType === 'glb';
  const useThreeJS = fileType === 'stl' || fileType === '3mf';

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="model-preview-overlay" onClick={handleBackdropClick}>
      <div className="model-preview-modal">
        <div className="model-preview-header">
          <h3>{artifact.filename}</h3>
          <button className="btn-close" onClick={onClose} title="Close (Esc)">
            &times;
          </button>
        </div>

        <div className="model-preview-content">
          {useModelViewer && (
            <model-viewer
              src={artifact.downloadUrl}
              alt={`3D preview of ${artifact.filename}`}
              auto-rotate
              camera-controls
              shadow-intensity="1"
              exposure="0.5"
              loading="eager"
              style={{ width: '100%', height: '100%' }}
            />
          )}

          {useThreeJS && (
            <div ref={containerRef} className="threejs-container">
              {loading && (
                <div className="preview-loading">
                  <div className="loader-spinner"></div>
                  <p>Loading {fileType.toUpperCase()} model...</p>
                </div>
              )}
              {error && (
                <div className="preview-error">
                  <p>{error}</p>
                </div>
              )}
            </div>
          )}

          {!isSupported && (
            <div className="preview-not-supported">
              <div className="preview-icon">📄</div>
              <p>Preview not available for {artifact.artifactType.toUpperCase()} files.</p>
              <p className="preview-hint">
                Download the file to view it in your preferred application.
              </p>
              <a
                href={artifact.downloadUrl}
                className="btn"
                download={artifact.filename}
                onClick={(e) => e.stopPropagation()}
              >
                Download {artifact.filename}
              </a>
            </div>
          )}
        </div>

        <div className="model-preview-footer">
          <div className="preview-info">
            <span className="preview-type">{artifact.artifactType.toUpperCase()}</span>
            {artifact.sizeBytes && (
              <span className="preview-size">
                {(artifact.sizeBytes / (1024 * 1024)).toFixed(1)} MB
              </span>
            )}
            {useThreeJS && (
              <span className="preview-hint-small">Drag to rotate, scroll to zoom</span>
            )}
          </div>
          <div className="preview-actions">
            <a
              href={artifact.downloadUrl}
              className="btn btn-primary"
              download={artifact.filename}
            >
              Download
            </a>
            <button className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModelPreview;
