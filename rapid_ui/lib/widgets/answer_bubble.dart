import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../models/query_response.dart';
import '../theme.dart';
import 'dept_badge.dart';
import 'confidence_bar.dart';

class UserBubble extends StatelessWidget {
  final String text;
  final String timestamp;
  final String? attachedFile;
  const UserBubble({super.key, required this.text, required this.timestamp, this.attachedFile});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 600),
        margin: const EdgeInsets.only(bottom: 16, left: 60),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: RapidColors.accent.withOpacity(0.15),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(14),
            topRight: Radius.circular(4),
            bottomLeft: Radius.circular(14),
            bottomRight: Radius.circular(14),
          ),
          border: Border.all(color: RapidColors.accent.withOpacity(0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Attached file chip
            if (attachedFile != null) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: RapidColors.accent.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.insert_drive_file_outlined, color: RapidColors.accent, size: 13),
                    const SizedBox(width: 5),
                    Text(
                      attachedFile!,
                      style: const TextStyle(color: RapidColors.accent, fontSize: 12, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
            ],
            Text(text, style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14)),
            const SizedBox(height: 4),
            Text(timestamp, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
          ],
        ),
      ),
    ).animate().fadeIn(duration: 200.ms).slideX(begin: 0.1, duration: 200.ms);
  }
}

class AnswerBubble extends StatefulWidget {
  final ChatMessage message;
  const AnswerBubble({super.key, required this.message});

  @override
  State<AnswerBubble> createState() => _AnswerBubbleState();
}

class _AnswerBubbleState extends State<AnswerBubble> {
  bool _sourcesExpanded = false;

  @override
  Widget build(BuildContext context) {
    final res = widget.message.response;
    final isError = res == null && widget.message.text.startsWith('Error:');
    final ts = '${widget.message.timestamp.hour.toString().padLeft(2,'0')}:${widget.message.timestamp.minute.toString().padLeft(2,'0')}';

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 720),
        margin: const EdgeInsets.only(bottom: 16, right: 60),
        decoration: BoxDecoration(
          color: isError ? RapidColors.error.withOpacity(0.1) : RapidColors.surface,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(14),
            bottomLeft: Radius.circular(14),
            bottomRight: Radius.circular(14),
          ),
          border: Border.all(
            color: isError ? RapidColors.error.withOpacity(0.4) : RapidColors.divider,
          ),
          boxShadow: isError ? null : const [
            BoxShadow(color: Color(0x0A000000), blurRadius: 8, offset: Offset(0, 2)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(
                children: [
                  Container(
                    width: 28, height: 28,
                    decoration: BoxDecoration(
                      color: RapidColors.accent.withOpacity(0.15),
                      shape: BoxShape.circle,
                      border: Border.all(color: RapidColors.accent.withOpacity(0.4)),
                    ),
                    child: const Center(
                      child: Text('R', style: TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w700, fontSize: 13)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text('RAPID', style: TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w600, fontSize: 13)),
                  const Spacer(),
                  Text(ts, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 11)),
                ],
              ),
            ),

            // Answer text
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              child: SelectableText(
                widget.message.text,
                style: const TextStyle(color: RapidColors.textPrimary, fontSize: 14, height: 1.55),
              ),
            ),

            if (res != null) ...[
              // Warning
              if (res.warning != null) ...[
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                  child: Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: RapidColors.warning.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: RapidColors.warning.withOpacity(0.4)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.warning_amber_rounded, color: RapidColors.warning, size: 16),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(res.warning!, style: const TextStyle(color: RapidColors.warning, fontSize: 12)),
                        ),
                      ],
                    ),
                  ),
                ),
              ],

              // Confidence + dept badges
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ConfidenceBar(confidence: res.confidence),
                    if (res.deptTags.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: res.deptTags.map((d) => DeptBadge(dept: d)).toList(),
                      ),
                    ],
                  ],
                ),
              ),

              // Sources (collapsible)
              if (res.sources.isNotEmpty) ...[
                InkWell(
                  onTap: () => setState(() => _sourcesExpanded = !_sourcesExpanded),
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: Row(
                      children: [
                        Icon(
                          _sourcesExpanded ? Icons.expand_less : Icons.expand_more,
                          color: RapidColors.textSecondary, size: 16,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${res.sources.length} source${res.sources.length > 1 ? 's' : ''}',
                          style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ),
                if (_sourcesExpanded)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: res.sources.map((s) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('• ', style: TextStyle(color: RapidColors.textSecondary)),
                            Expanded(
                              child: Text(s, style: const TextStyle(color: RapidColors.textSecondary, fontSize: 12)),
                            ),
                          ],
                        ),
                      )).toList(),
                    ),
                  ),
              ],
            ],
          ],
        ),
      ),
    ).animate().fadeIn(duration: 300.ms).slideX(begin: -0.05, duration: 300.ms);
  }
}

class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: RapidColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: RapidColors.divider),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('RAPID is thinking', style: TextStyle(color: RapidColors.textSecondary, fontSize: 13)),
            const SizedBox(width: 8),
            ...List.generate(3, (i) => Container(
              margin: const EdgeInsets.symmetric(horizontal: 2),
              width: 6, height: 6,
              decoration: const BoxDecoration(color: RapidColors.accent, shape: BoxShape.circle),
            ).animate(onPlay: (c) => c.repeat()).fadeIn(delay: (i * 200).ms).then().fadeOut()),
          ],
        ),
      ),
    );
  }
}
