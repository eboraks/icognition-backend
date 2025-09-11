"""
Content Validation Service for ensuring extracted content quality
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from app.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationLevel(Enum):
    """Content validation levels"""
    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


class ValidationResult(Enum):
    """Validation result types"""
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    FLAGGED = "flagged"


@dataclass
class ContentValidationRule:
    """Individual content validation rule"""
    name: str
    description: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    required: bool = True
    weight: float = 1.0


@dataclass
class ValidationIssue:
    """Individual validation issue"""
    rule_name: str
    severity: ValidationResult
    message: str
    actual_value: Optional[float] = None
    expected_value: Optional[float] = None
    suggestion: Optional[str] = None


@dataclass
class ContentValidationReport:
    """Complete content validation report"""
    is_valid: bool
    overall_score: float
    validation_level: ValidationLevel
    issues: List[ValidationIssue]
    warnings: List[ValidationIssue]
    passed_rules: List[str]
    failed_rules: List[str]
    content_metrics: Dict[str, Any]
    validation_timestamp: datetime
    processing_time: float


class ContentValidationService:
    """
    Service for validating extracted content quality and completeness
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.MODERATE):
        """
        Initialize the content validation service
        
        Args:
            validation_level: Level of validation strictness
        """
        self.validation_level = validation_level
        self.rules = self._initialize_validation_rules()
        logger.info(f"ContentValidationService initialized with {validation_level.value} validation level")
    
    def _initialize_validation_rules(self) -> Dict[str, ContentValidationRule]:
        """Initialize validation rules based on validation level"""
        base_rules = {
            "min_content_length": ContentValidationRule(
                name="min_content_length",
                description="Minimum content length in characters",
                min_value=100,
                required=True,
                weight=2.0
            ),
            "min_word_count": ContentValidationRule(
                name="min_word_count",
                description="Minimum word count",
                min_value=20,
                required=True,
                weight=2.0
            ),
            "min_sentence_count": ContentValidationRule(
                name="min_sentence_count",
                description="Minimum number of sentences",
                min_value=3,
                required=True,
                weight=1.5
            ),
            "min_paragraph_count": ContentValidationRule(
                name="min_paragraph_count",
                description="Minimum number of paragraphs",
                min_value=1,
                required=True,
                weight=1.0
            ),
            "max_content_length": ContentValidationRule(
                name="max_content_length",
                description="Maximum content length in characters",
                max_value=1000000,
                required=False,
                weight=0.5
            ),
            "readability_score": ContentValidationRule(
                name="readability_score",
                description="Content readability score",
                min_value=0.3,
                required=False,
                weight=1.0
            ),
            "content_diversity": ContentValidationRule(
                name="content_diversity",
                description="Content diversity score",
                min_value=0.2,
                required=False,
                weight=1.0
            ),
            "no_excessive_repetition": ContentValidationRule(
                name="no_excessive_repetition",
                description="No excessive word repetition",
                max_value=0.3,
                required=True,
                weight=1.5
            ),
            "has_meaningful_content": ContentValidationRule(
                name="has_meaningful_content",
                description="Content contains meaningful information",
                min_value=0.5,
                required=True,
                weight=2.0
            )
        }
        
        # Adjust rules based on validation level
        if self.validation_level == ValidationLevel.STRICT:
            base_rules["min_content_length"].min_value = 500
            base_rules["min_word_count"].min_value = 75
            base_rules["min_sentence_count"].min_value = 5
            base_rules["min_paragraph_count"].min_value = 2
        elif self.validation_level == ValidationLevel.LENIENT:
            base_rules["min_content_length"].min_value = 50
            base_rules["min_word_count"].min_value = 10
            base_rules["min_sentence_count"].min_value = 2
            base_rules["min_paragraph_count"].min_value = 1
        
        return base_rules
    
    async def validate_content(
        self,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ContentValidationReport:
        """
        Validate extracted content quality
        
        Args:
            content: Extracted content to validate
            title: Document title (optional)
            url: Document URL (optional)
            metadata: Additional metadata (optional)
            
        Returns:
            ContentValidationReport with validation results
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"Starting content validation for content of length {len(content)}")
            
            # Calculate content metrics
            metrics = self._calculate_content_metrics(content, title, url, metadata)
            
            # Validate against rules
            issues = []
            warnings = []
            passed_rules = []
            failed_rules = []
            
            for rule_name, rule in self.rules.items():
                try:
                    validation_result = self._validate_rule(rule, metrics)
                    
                    if validation_result.is_valid:
                        passed_rules.append(rule_name)
                    else:
                        failed_rules.append(rule_name)
                        
                        if rule.required:
                            issues.append(validation_result.issue)
                        else:
                            warnings.append(validation_result.issue)
                            
                except Exception as e:
                    logger.warning(f"Error validating rule {rule_name}: {str(e)}")
                    failed_rules.append(rule_name)
                    issues.append(ValidationIssue(
                        rule_name=rule_name,
                        severity=ValidationResult.INVALID,
                        message=f"Validation error: {str(e)}"
                    ))
            
            # Calculate overall score
            overall_score = self._calculate_overall_score(metrics, passed_rules, failed_rules)
            
            # Determine if content is valid
            is_valid = len(issues) == 0 and overall_score >= 0.6
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            report = ContentValidationReport(
                is_valid=is_valid,
                overall_score=overall_score,
                validation_level=self.validation_level,
                issues=issues,
                warnings=warnings,
                passed_rules=passed_rules,
                failed_rules=failed_rules,
                content_metrics=metrics,
                validation_timestamp=datetime.now(),
                processing_time=processing_time
            )
            
            logger.info(f"Content validation completed: {len(issues)} issues, {len(warnings)} warnings, score: {overall_score:.2f}")
            
            return report
            
        except Exception as e:
            logger.error(f"Error during content validation: {str(e)}")
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return ContentValidationReport(
                is_valid=False,
                overall_score=0.0,
                validation_level=self.validation_level,
                issues=[ValidationIssue(
                    rule_name="validation_error",
                    severity=ValidationResult.INVALID,
                    message=f"Validation failed: {str(e)}"
                )],
                warnings=[],
                passed_rules=[],
                failed_rules=list(self.rules.keys()),
                content_metrics={},
                validation_timestamp=datetime.now(),
                processing_time=processing_time
            )
    
    def _calculate_content_metrics(
        self,
        content: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Calculate comprehensive content metrics"""
        try:
            # Basic metrics
            content_length = len(content)
            word_count = len(content.split())
            sentence_count = len(re.findall(r'[.!?]+', content))
            paragraph_count = len([p for p in content.split('\n\n') if p.strip()])
            
            # Advanced metrics
            readability_score = self._calculate_readability_score(content)
            diversity_score = self._calculate_diversity_score(content)
            repetition_score = self._calculate_repetition_score(content)
            meaningful_score = self._calculate_meaningful_score(content, title)
            
            # URL and metadata analysis
            has_url = bool(url and url.strip())
            has_title = bool(title and title.strip())
            has_metadata = bool(metadata)
            
            return {
                'content_length': content_length,
                'word_count': word_count,
                'sentence_count': sentence_count,
                'paragraph_count': paragraph_count,
                'readability_score': readability_score,
                'diversity_score': diversity_score,
                'repetition_score': repetition_score,
                'meaningful_score': meaningful_score,
                'has_url': has_url,
                'has_title': has_title,
                'has_metadata': has_metadata,
                'avg_words_per_sentence': word_count / max(sentence_count, 1),
                'avg_words_per_paragraph': word_count / max(paragraph_count, 1),
                'char_to_word_ratio': content_length / max(word_count, 1)
            }
            
        except Exception as e:
            logger.error(f"Error calculating content metrics: {str(e)}")
            return {
                'content_length': len(content),
                'word_count': 0,
                'sentence_count': 0,
                'paragraph_count': 0,
                'readability_score': 0.0,
                'diversity_score': 0.0,
                'repetition_score': 1.0,
                'meaningful_score': 0.0,
                'has_url': False,
                'has_title': False,
                'has_metadata': False,
                'avg_words_per_sentence': 0.0,
                'avg_words_per_paragraph': 0.0,
                'char_to_word_ratio': 0.0
            }
    
    def _calculate_readability_score(self, content: str) -> float:
        """Calculate content readability score"""
        try:
            words = content.split()
            sentences = re.findall(r'[.!?]+', content)
            
            if not words or not sentences:
                return 0.0
            
            # Simple readability based on average words per sentence
            avg_words_per_sentence = len(words) / len(sentences)
            
            # Normalize to 0-1 scale (optimal range: 10-20 words per sentence)
            if avg_words_per_sentence <= 10:
                return 0.5 + (avg_words_per_sentence / 10) * 0.5
            elif avg_words_per_sentence <= 20:
                return 1.0
            else:
                return max(0.0, 1.0 - (avg_words_per_sentence - 20) / 20)
                
        except Exception:
            return 0.0
    
    def _calculate_diversity_score(self, content: str) -> float:
        """Calculate content diversity score based on unique words"""
        try:
            words = [word.lower().strip('.,!?;:"()[]{}') for word in content.split()]
            unique_words = set(words)
            
            if not words:
                return 0.0
            
            # Diversity ratio (unique words / total words)
            diversity_ratio = len(unique_words) / len(words)
            
            # Normalize to 0-1 scale
            return min(1.0, diversity_ratio * 2)  # Scale up since typical ratio is 0.3-0.7
            
        except Exception:
            return 0.0
    
    def _calculate_repetition_score(self, content: str) -> float:
        """Calculate repetition score (higher = more repetitive)"""
        try:
            words = [word.lower().strip('.,!?;:"()[]{}') for word in content.split()]
            
            if not words:
                return 0.0
            
            # Count word frequencies
            word_counts = {}
            for word in words:
                if len(word) > 3:  # Only count words longer than 3 characters
                    word_counts[word] = word_counts.get(word, 0) + 1
            
            if not word_counts:
                return 0.0
            
            # Calculate repetition ratio
            total_words = len(words)
            repeated_words = sum(count for count in word_counts.values() if count > 1)
            
            return repeated_words / total_words
            
        except Exception:
            return 0.0
    
    def _calculate_meaningful_score(self, content: str, title: Optional[str] = None) -> float:
        """Calculate how meaningful the content is"""
        try:
            score = 0.0
            
            # Check for meaningful indicators
            meaningful_indicators = [
                r'\b(article|blog|post|news|report|analysis|study|research)\b',
                r'\b(according|research|study|analysis|report|findings)\b',
                r'\b(data|statistics|results|conclusion|summary)\b',
                r'\b(however|therefore|furthermore|moreover|additionally)\b'
            ]
            
            content_lower = content.lower()
            for pattern in meaningful_indicators:
                if re.search(pattern, content_lower):
                    score += 0.2
            
            # Check for title-content alignment
            if title:
                title_words = set(title.lower().split())
                content_words = set(content.lower().split())
                if title_words and content_words:
                    overlap = len(title_words.intersection(content_words))
                    score += min(0.3, overlap / len(title_words))
            
            # Check for structured content (headings, lists, etc.)
            if re.search(r'#{1,6}\s+', content):  # Markdown headings
                score += 0.1
            if re.search(r'^\s*[-*+]\s+', content, re.MULTILINE):  # Lists
                score += 0.1
            if re.search(r'\d+\.\s+', content):  # Numbered lists
                score += 0.1
            
            return min(1.0, score)
            
        except Exception:
            return 0.0
    
    def _validate_rule(self, rule: ContentValidationRule, metrics: Dict[str, Any]) -> 'RuleValidationResult':
        """Validate a single rule against content metrics"""
        try:
            # Map rule names to metric names
            metric_mapping = {
                'min_content_length': 'content_length',
                'max_content_length': 'content_length',
                'min_word_count': 'word_count',
                'min_sentence_count': 'sentence_count',
                'min_paragraph_count': 'paragraph_count',
                'readability_score': 'readability_score',
                'content_diversity': 'diversity_score',
                'no_excessive_repetition': 'repetition_score',
                'has_meaningful_content': 'meaningful_score'
            }
            
            metric_name = metric_mapping.get(rule.name)
            if not metric_name:
                return RuleValidationResult(
                    is_valid=False,
                    issue=ValidationIssue(
                        rule_name=rule.name,
                        severity=ValidationResult.INVALID,
                        message=f"Unknown validation rule: {rule.name}"
                    )
                )
            
            actual_value = metrics.get(metric_name)
            
            if actual_value is None:
                return RuleValidationResult(
                    is_valid=False,
                    issue=ValidationIssue(
                        rule_name=rule.name,
                        severity=ValidationResult.INVALID,
                        message=f"Could not calculate {rule.name}",
                        actual_value=None,
                        expected_value=rule.min_value or rule.max_value
                    )
                )
            
            # Check minimum value
            if rule.min_value is not None and actual_value < rule.min_value:
                return RuleValidationResult(
                    is_valid=False,
                    issue=ValidationIssue(
                        rule_name=rule.name,
                        severity=ValidationResult.INVALID if rule.required else ValidationResult.WARNING,
                        message=f"{rule.description}: {actual_value} is below minimum {rule.min_value}",
                        actual_value=actual_value,
                        expected_value=rule.min_value,
                        suggestion=f"Increase content length to at least {rule.min_value}"
                    )
                )
            
            # Check maximum value
            if rule.max_value is not None and actual_value > rule.max_value:
                return RuleValidationResult(
                    is_valid=False,
                    issue=ValidationIssue(
                        rule_name=rule.name,
                        severity=ValidationResult.INVALID if rule.required else ValidationResult.WARNING,
                        message=f"{rule.description}: {actual_value} exceeds maximum {rule.max_value}",
                        actual_value=actual_value,
                        expected_value=rule.max_value,
                        suggestion=f"Reduce content length to at most {rule.max_value}"
                    )
                )
            
            return RuleValidationResult(is_valid=True, issue=None)
            
        except Exception as e:
            return RuleValidationResult(
                is_valid=False,
                issue=ValidationIssue(
                    rule_name=rule.name,
                    severity=ValidationResult.INVALID,
                    message=f"Validation error: {str(e)}"
                )
            )
    
    def _calculate_overall_score(
        self,
        metrics: Dict[str, Any],
        passed_rules: List[str],
        failed_rules: List[str]
    ) -> float:
        """Calculate overall validation score"""
        try:
            if not self.rules:
                return 0.0
            
            total_weight = sum(rule.weight for rule in self.rules.values())
            passed_weight = sum(self.rules[rule].weight for rule in passed_rules)
            
            base_score = passed_weight / total_weight if total_weight > 0 else 0.0
            
            # Bonus for good metrics
            bonus = 0.0
            if metrics.get('readability_score', 0) > 0.7:
                bonus += 0.1
            if metrics.get('diversity_score', 0) > 0.5:
                bonus += 0.1
            if metrics.get('meaningful_score', 0) > 0.6:
                bonus += 0.1
            
            return min(1.0, base_score + bonus)
            
        except Exception:
            return 0.0
    
    def get_validation_summary(self, report: ContentValidationReport) -> Dict[str, Any]:
        """Get a summary of validation results"""
        return {
            'is_valid': report.is_valid,
            'overall_score': report.overall_score,
            'validation_level': report.validation_level.value,
            'total_issues': len(report.issues),
            'total_warnings': len(report.warnings),
            'passed_rules': len(report.passed_rules),
            'failed_rules': len(report.failed_rules),
            'content_length': report.content_metrics.get('content_length', 0),
            'word_count': report.content_metrics.get('word_count', 0),
            'processing_time': report.processing_time
        }


@dataclass
class RuleValidationResult:
    """Result of validating a single rule"""
    is_valid: bool
    issue: Optional[ValidationIssue]


# Global service instance
_content_validation_service: Optional[ContentValidationService] = None


def get_content_validation_service(validation_level: ValidationLevel = ValidationLevel.MODERATE) -> ContentValidationService:
    """Get the global content validation service instance"""
    global _content_validation_service
    if _content_validation_service is None or _content_validation_service.validation_level != validation_level:
        _content_validation_service = ContentValidationService(validation_level)
    return _content_validation_service


def initialize_content_validation_service(validation_level: ValidationLevel = ValidationLevel.MODERATE) -> ContentValidationService:
    """Initialize the global content validation service instance"""
    global _content_validation_service
    _content_validation_service = ContentValidationService(validation_level)
    return _content_validation_service
