import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// ── RAPID Brand Colours — Light Theme ─────────────────────────────────────────
class RapidColors {
  static const primary     = Color(0xFFF8FAFC); // page background (light blue-grey)
  static const surface     = Color(0xFFFFFFFF); // card / panel surface
  static const surfaceAlt  = Color(0xFFF1F5F9); // secondary fills, inputs
  static const accent      = Color(0xFF2563EB); // brand blue
  static const accentDim   = Color(0xFF1D4ED8); // darker blue for hover/active
  static const textPrimary   = Color(0xFF0F172A); // near-black
  static const textSecondary = Color(0xFF64748B); // slate grey
  static const success = Color(0xFF16A34A);
  static const warning = Color(0xFFD97706);
  static const error   = Color(0xFFDC2626);
  static const divider = Color(0xFFE2E8F0); // subtle separator

  // Department colours (kept vivid — they appear as small coloured badges)
  static const Map<String, Color> deptColors = {
    'hr':               Color(0xFF7C3AED),
    'finance':          Color(0xFF059669),
    'legal':            Color(0xFFDC2626),
    'sales':            Color(0xFF2563EB),
    'marketing':        Color(0xFFDB2777),
    'ops':              Color(0xFFD97706),
    'it':               Color(0xFF0891B2),
    'procurement':      Color(0xFF65A30D),
    'rd':               Color(0xFF7C3AED),
    'customer_success': Color(0xFF0D9488),
  };
}

// ── Department emoji map ──────────────────────────────────────────────────────
const Map<String, String> deptEmoji = {
  'hr':               '👥',
  'finance':          '💰',
  'legal':            '⚖️',
  'sales':            '🛒',
  'marketing':        '📈',
  'ops':              '⚙️',
  'it':               '💻',
  'procurement':      '📦',
  'rd':               '🔬',
  'customer_success': '🎯',
};

const Map<String, String> deptLabel = {
  'hr':               'HR',
  'finance':          'Finance',
  'legal':            'Legal',
  'sales':            'Sales',
  'marketing':        'Marketing',
  'ops':              'Operations',
  'it':               'IT',
  'procurement':      'Procurement',
  'rd':               'R&D',
  'customer_success': 'CS',
};

// ── App Theme ─────────────────────────────────────────────────────────────────
ThemeData get rapidTheme => ThemeData(
  useMaterial3: true,
  brightness: Brightness.light,
  scaffoldBackgroundColor: RapidColors.primary,
  colorScheme: const ColorScheme.light(
    primary:   RapidColors.accent,
    secondary: RapidColors.accentDim,
    surface:   RapidColors.surface,
    error:     RapidColors.error,
    onPrimary: Colors.white,
    onSurface: RapidColors.textPrimary,
  ),
  textTheme: GoogleFonts.interTextTheme(
    const TextTheme(
      displayLarge:   TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w700),
      headlineMedium: TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600),
      titleLarge:     TextStyle(color: RapidColors.textPrimary, fontWeight: FontWeight.w600),
      titleMedium:    TextStyle(color: RapidColors.textPrimary),
      bodyLarge:      TextStyle(color: RapidColors.textPrimary),
      bodyMedium:     TextStyle(color: RapidColors.textSecondary),
      labelLarge:     TextStyle(color: RapidColors.accent, fontWeight: FontWeight.w600),
    ),
  ),
  cardTheme: const CardThemeData(
    color: RapidColors.surface,
    elevation: 0,
    margin: EdgeInsets.zero,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.all(Radius.circular(12)),
      side: BorderSide(color: RapidColors.divider),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: RapidColors.surfaceAlt,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: RapidColors.divider),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: RapidColors.divider),
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: RapidColors.accent, width: 1.5),
    ),
    hintStyle: const TextStyle(color: RapidColors.textSecondary),
    labelStyle: const TextStyle(color: RapidColors.textSecondary),
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      backgroundColor: RapidColors.accent,
      foregroundColor: Colors.white,
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 15),
      elevation: 0,
    ),
  ),
  dividerTheme: const DividerThemeData(color: RapidColors.divider, thickness: 1),
  appBarTheme: const AppBarTheme(
    backgroundColor: RapidColors.surface,
    foregroundColor: RapidColors.textPrimary,
    elevation: 0,
    scrolledUnderElevation: 1,
    shadowColor: RapidColors.divider,
    titleTextStyle: TextStyle(
      color: RapidColors.textPrimary, fontSize: 18, fontWeight: FontWeight.w600,
    ),
  ),
  popupMenuTheme: const PopupMenuThemeData(
    color: RapidColors.surface,
    elevation: 4,
    shadowColor: Color(0x1A000000),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.all(Radius.circular(10)),
      side: BorderSide(color: RapidColors.divider),
    ),
  ),
  chipTheme: const ChipThemeData(
    backgroundColor: RapidColors.surfaceAlt,
    selectedColor: Color(0xFFDBEAFE), // blue-100
    labelStyle: TextStyle(fontSize: 12),
    side: BorderSide(color: RapidColors.divider),
  ),
);
