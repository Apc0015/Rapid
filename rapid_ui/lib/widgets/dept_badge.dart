import 'package:flutter/material.dart';
import '../theme.dart';

class DeptBadge extends StatelessWidget {
  final String dept;
  const DeptBadge({super.key, required this.dept});

  @override
  Widget build(BuildContext context) {
    final color = RapidColors.deptColors[dept] ?? RapidColors.accent;
    final emoji = deptEmoji[dept] ?? '🏢';
    final label = deptLabel[dept] ?? dept.toUpperCase();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.18),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.5), width: 0.8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(emoji, style: const TextStyle(fontSize: 11)),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }
}
