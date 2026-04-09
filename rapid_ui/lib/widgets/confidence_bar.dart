import 'package:flutter/material.dart';
import '../theme.dart';

class ConfidenceBar extends StatelessWidget {
  final double confidence;
  const ConfidenceBar({super.key, required this.confidence});

  Color get _color {
    if (confidence >= 0.65) return RapidColors.success;
    if (confidence >= 0.40) return RapidColors.warning;
    return RapidColors.error;
  }

  String get _label {
    if (confidence >= 0.65) return 'High confidence';
    if (confidence >= 0.40) return 'Moderate confidence';
    return 'Low confidence';
  }

  @override
  Widget build(BuildContext context) {
    final pct = (confidence * 100).toStringAsFixed(0);
    return Row(
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: confidence.clamp(0.0, 1.0),
              backgroundColor: RapidColors.divider,
              valueColor: AlwaysStoppedAnimation<Color>(_color),
              minHeight: 4,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          '$pct% — $_label',
          style: TextStyle(
            color: _color,
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}
