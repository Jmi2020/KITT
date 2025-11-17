"""Print Success Predictor - P3 #16 ML-based Failure Prediction.

Predicts print success/failure probability based on historical outcomes.
Uses lightweight machine learning (sklearn) to analyze patterns in:
- Material + printer combinations
- Print settings (temps, speeds, infill)
- Success/failure history

Provides success probability (0-100%) and setting recommendations.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import PrintOutcome
from common.logging import get_logger

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

LOGGER = get_logger(__name__)


@dataclass
class PredictionResult:
    """Result of success prediction."""

    success_probability: float  # 0.0 - 1.0
    risk_level: str  # "low", "medium", "high"
    confidence: float  # Model confidence 0.0 - 1.0
    recommendations: List[str]
    feature_importance: Dict[str, float]
    similar_prints_count: int
    similar_success_rate: float


@dataclass
class PrintFeatures:
    """Extracted features for ML model."""

    material_id: str
    printer_id: str
    nozzle_temp: float
    bed_temp: float
    print_speed: float  # mm/s
    layer_height: float  # mm
    infill_percent: float
    supports_enabled: bool

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "material_id": self.material_id,
            "printer_id": self.printer_id,
            "nozzle_temp": self.nozzle_temp,
            "bed_temp": self.bed_temp,
            "print_speed": self.print_speed,
            "layer_height": self.layer_height,
            "infill_percent": self.infill_percent,
            "supports_enabled": int(self.supports_enabled),
        }


class PrintSuccessPredictor:
    """ML-based print success prediction.

    Training Process:
    1. Load historical print outcomes (min 20 required)
    2. Extract features (material, printer, settings)
    3. Encode categorical variables
    4. Train Random Forest classifier
    5. Save model to disk

    Prediction Process:
    1. Load trained model
    2. Extract features from job settings
    3. Predict success probability
    4. Calculate risk level
    5. Generate recommendations based on similar failures
    """

    MIN_TRAINING_SAMPLES = 20  # Minimum outcomes needed for training
    MODEL_PATH = Path("models/print_success_predictor.pkl")
    ENCODERS_PATH = Path("models/feature_encoders.pkl")

    def __init__(self, db: Session, model_dir: Optional[Path] = None):
        """Initialize predictor.

        Args:
            db: Database session
            model_dir: Optional model directory (default: models/)
        """
        self.db = db

        if model_dir:
            self.model_path = model_dir / "print_success_predictor.pkl"
            self.encoders_path = model_dir / "feature_encoders.pkl"
        else:
            self.model_path = self.MODEL_PATH
            self.encoders_path = self.ENCODERS_PATH

        # Ensure model directory exists
        self.model_path.parent.mkdir(parents=True, exist_ok=True)

        # ML components (loaded on demand)
        self.model: Optional[RandomForestClassifier] = None
        self.material_encoder: Optional[LabelEncoder] = None
        self.printer_encoder: Optional[LabelEncoder] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False

        # Load existing model if available
        self._load_model()

    def _load_model(self) -> bool:
        """Load trained model from disk.

        Returns:
            True if model loaded successfully
        """
        if not SKLEARN_AVAILABLE:
            LOGGER.warning("sklearn not available - predictions disabled")
            return False

        if not self.model_path.exists() or not self.encoders_path.exists():
            LOGGER.info("No trained model found - training required")
            return False

        try:
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)

            with open(self.encoders_path, "rb") as f:
                encoders = pickle.load(f)
                self.material_encoder = encoders["material"]
                self.printer_encoder = encoders["printer"]
                self.scaler = encoders["scaler"]

            self.is_trained = True
            LOGGER.info("Loaded trained model", model_path=str(self.model_path))
            return True

        except Exception as e:
            LOGGER.error("Failed to load model", error=str(e), exc_info=True)
            return False

    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.model_path, "wb") as f:
                pickle.dump(self.model, f)

            encoders = {
                "material": self.material_encoder,
                "printer": self.printer_encoder,
                "scaler": self.scaler,
            }
            with open(self.encoders_path, "wb") as f:
                pickle.dump(encoders, f)

            LOGGER.info("Saved trained model", model_path=str(self.model_path))

        except Exception as e:
            LOGGER.error("Failed to save model", error=str(e), exc_info=True)

    def train(self, min_outcomes: int = MIN_TRAINING_SAMPLES) -> bool:
        """Train prediction model on historical outcomes.

        Args:
            min_outcomes: Minimum number of outcomes required (default: 20)

        Returns:
            True if training successful
        """
        if not SKLEARN_AVAILABLE:
            LOGGER.error("sklearn not available - cannot train model")
            return False

        LOGGER.info("Starting model training", min_outcomes=min_outcomes)

        # Load historical outcomes
        outcomes = self._load_training_data()

        if len(outcomes) < min_outcomes:
            LOGGER.warning(
                "Insufficient training data",
                outcomes=len(outcomes),
                required=min_outcomes,
            )
            return False

        # Extract features and labels
        features_list = []
        labels = []

        for outcome in outcomes:
            try:
                features = self._extract_features_from_outcome(outcome)
                features_list.append(features)
                labels.append(1 if outcome.success else 0)
            except Exception as e:
                LOGGER.warning(
                    "Failed to extract features",
                    outcome_id=outcome.id,
                    error=str(e),
                )
                continue

        if len(features_list) < min_outcomes:
            LOGGER.warning("Too few valid feature extractions")
            return False

        # Prepare feature matrix
        X, feature_names = self._prepare_feature_matrix(features_list)
        y = np.array(labels)

        # Train model
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            class_weight="balanced",  # Handle imbalanced data
        )

        self.model.fit(X, y)

        # Calculate training accuracy
        train_accuracy = self.model.score(X, y)

        LOGGER.info(
            "Model training complete",
            samples=len(X),
            features=X.shape[1],
            accuracy=f"{train_accuracy:.2%}",
        )

        self.is_trained = True
        self._save_model()

        return True

    def _load_training_data(self) -> List[PrintOutcome]:
        """Load historical print outcomes for training.

        Returns:
            List of print outcomes
        """
        # Load outcomes from last 6 months (fresher data more relevant)
        cutoff_date = datetime.utcnow() - timedelta(days=180)

        stmt = (
            select(PrintOutcome)
            .where(PrintOutcome.measured_at >= cutoff_date)
            .order_by(PrintOutcome.measured_at.desc())
        )

        outcomes = self.db.execute(stmt).scalars().all()

        LOGGER.info(
            "Loaded training data",
            outcomes=len(outcomes),
            success_count=sum(1 for o in outcomes if o.success),
            failure_count=sum(1 for o in outcomes if not o.success),
        )

        return outcomes

    def _extract_features_from_outcome(self, outcome: PrintOutcome) -> PrintFeatures:
        """Extract features from print outcome.

        Args:
            outcome: Print outcome record

        Returns:
            Extracted features
        """
        settings = outcome.print_settings

        return PrintFeatures(
            material_id=outcome.material_id,
            printer_id=outcome.printer_id,
            nozzle_temp=settings.get("nozzle_temp", 210.0),
            bed_temp=settings.get("bed_temp", 60.0),
            print_speed=settings.get("speed", 50.0),
            layer_height=settings.get("layer_height", 0.2),
            infill_percent=settings.get("infill", 20.0),
            supports_enabled=settings.get("supports_enabled", False),
        )

    def _prepare_feature_matrix(
        self,
        features_list: List[PrintFeatures],
    ) -> Tuple[np.ndarray, List[str]]:
        """Prepare feature matrix for sklearn.

        Args:
            features_list: List of extracted features

        Returns:
            (feature_matrix, feature_names) tuple
        """
        # Initialize encoders if needed
        if self.material_encoder is None:
            self.material_encoder = LabelEncoder()
            self.printer_encoder = LabelEncoder()
            self.scaler = StandardScaler()

            # Fit encoders
            materials = [f.material_id for f in features_list]
            printers = [f.printer_id for f in features_list]

            self.material_encoder.fit(materials)
            self.printer_encoder.fit(printers)

        # Build feature matrix
        feature_matrix = []

        for features in features_list:
            row = [
                self.material_encoder.transform([features.material_id])[0],
                self.printer_encoder.transform([features.printer_id])[0],
                features.nozzle_temp,
                features.bed_temp,
                features.print_speed,
                features.layer_height,
                features.infill_percent,
                int(features.supports_enabled),
            ]
            feature_matrix.append(row)

        X = np.array(feature_matrix)

        # Scale numerical features (columns 2-7)
        X[:, 2:] = self.scaler.fit_transform(X[:, 2:])

        feature_names = [
            "material_encoded",
            "printer_encoded",
            "nozzle_temp",
            "bed_temp",
            "print_speed",
            "layer_height",
            "infill_percent",
            "supports_enabled",
        ]

        return X, feature_names

    async def predict(
        self,
        features: PrintFeatures,
    ) -> PredictionResult:
        """Predict success probability for print job.

        Args:
            features: Print job features

        Returns:
            Prediction result with probability and recommendations
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained - call train() first")

        # Prepare feature vector
        try:
            feature_vec = np.array([[
                self.material_encoder.transform([features.material_id])[0],
                self.printer_encoder.transform([features.printer_id])[0],
                features.nozzle_temp,
                features.bed_temp,
                features.print_speed,
                features.layer_height,
                features.infill_percent,
                int(features.supports_enabled),
            ]])

            # Scale numerical features
            feature_vec[:, 2:] = self.scaler.transform(feature_vec[:, 2:])

        except ValueError as e:
            # Unknown material or printer
            LOGGER.warning("Unknown material/printer", error=str(e))
            return self._fallback_prediction(features)

        # Predict
        prob = self.model.predict_proba(feature_vec)[0][1]  # Probability of success
        confidence = max(self.model.predict_proba(feature_vec)[0])  # Max class probability

        # Determine risk level
        if prob >= 0.8:
            risk_level = "low"
        elif prob >= 0.6:
            risk_level = "medium"
        else:
            risk_level = "high"

        # Find similar prints
        similar_outcomes = self._find_similar_prints(features)
        similar_count = len(similar_outcomes)
        similar_success_rate = (
            sum(1 for o in similar_outcomes if o.success) / similar_count
            if similar_count > 0
            else 0.0
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            features,
            prob,
            similar_outcomes,
        )

        # Feature importance
        feature_importance = dict(zip(
            ["material", "printer", "nozzle_temp", "bed_temp", "speed", "layer_height", "infill", "supports"],
            self.model.feature_importances_,
        ))

        return PredictionResult(
            success_probability=prob,
            risk_level=risk_level,
            confidence=confidence,
            recommendations=recommendations,
            feature_importance=feature_importance,
            similar_prints_count=similar_count,
            similar_success_rate=similar_success_rate,
        )

    def _fallback_prediction(self, features: PrintFeatures) -> PredictionResult:
        """Fallback prediction for unknown materials/printers.

        Args:
            features: Print features

        Returns:
            Conservative prediction
        """
        return PredictionResult(
            success_probability=0.5,  # 50% - unknown
            risk_level="medium",
            confidence=0.3,  # Low confidence
            recommendations=[
                "Unknown material or printer - limited historical data",
                "Consider test print with conservative settings",
                "Monitor first layer closely",
            ],
            feature_importance={},
            similar_prints_count=0,
            similar_success_rate=0.0,
        )

    def _find_similar_prints(
        self,
        features: PrintFeatures,
        max_results: int = 20,
    ) -> List[PrintOutcome]:
        """Find similar historical prints.

        Args:
            features: Target print features
            max_results: Maximum results to return

        Returns:
            List of similar print outcomes
        """
        # Query outcomes with same material + printer
        stmt = (
            select(PrintOutcome)
            .where(
                PrintOutcome.material_id == features.material_id,
                PrintOutcome.printer_id == features.printer_id,
            )
            .order_by(PrintOutcome.measured_at.desc())
            .limit(max_results)
        )

        similar_outcomes = self.db.execute(stmt).scalars().all()

        return similar_outcomes

    def _generate_recommendations(
        self,
        features: PrintFeatures,
        success_prob: float,
        similar_outcomes: List[PrintOutcome],
    ) -> List[str]:
        """Generate setting recommendations based on prediction.

        Args:
            features: Print features
            success_prob: Predicted success probability
            similar_outcomes: Similar historical prints

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Low success probability - suggest adjustments
        if success_prob < 0.6:
            recommendations.append("⚠️ HIGH RISK - Consider adjusting settings")

            # Analyze failures in similar prints
            failures = [o for o in similar_outcomes if not o.success]

            if failures:
                # Common failure reasons
                failure_reasons = {}
                for failure in failures:
                    reason = failure.failure_reason or "unknown"
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

                # Most common failure
                if failure_reasons:
                    most_common = max(failure_reasons, key=failure_reasons.get)
                    recommendations.append(f"Common failure: {most_common}")

                    # Setting suggestions based on failure type
                    if "adhesion" in most_common.lower():
                        recommendations.append("Try: Increase bed temp by 5°C")
                        recommendations.append("Try: Decrease first layer speed")
                        recommendations.append("Try: Enable brim or raft")
                    elif "warping" in most_common.lower():
                        recommendations.append("Try: Increase bed temp")
                        recommendations.append("Try: Enable enclosure/draft shield")
                    elif "stringing" in most_common.lower():
                        recommendations.append("Try: Decrease nozzle temp by 5°C")
                        recommendations.append("Try: Increase retraction distance")
                    elif "layer" in most_common.lower():
                        recommendations.append("Try: Decrease layer height to 0.15mm")
                        recommendations.append("Try: Decrease print speed")

        # Medium probability - proceed with caution
        elif success_prob < 0.8:
            recommendations.append("⚙️ MODERATE RISK - Monitor print closely")
            recommendations.append("Watch first layer for adhesion issues")

        # High probability - good to go
        else:
            recommendations.append("✅ LOW RISK - Settings look good")
            if similar_outcomes:
                success_count = sum(1 for o in similar_outcomes if o.success)
                recommendations.append(
                    f"Based on {success_count}/{len(similar_outcomes)} successful similar prints"
                )

        return recommendations

    def get_training_status(self) -> dict:
        """Get model training status.

        Returns:
            Dict with training info
        """
        outcome_count = self.db.query(PrintOutcome).count()

        return {
            "is_trained": self.is_trained,
            "model_exists": self.model_path.exists(),
            "total_outcomes": outcome_count,
            "min_required": self.MIN_TRAINING_SAMPLES,
            "ready_to_train": outcome_count >= self.MIN_TRAINING_SAMPLES,
            "sklearn_available": SKLEARN_AVAILABLE,
        }
