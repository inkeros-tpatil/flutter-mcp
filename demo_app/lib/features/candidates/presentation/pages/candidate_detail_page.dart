import 'package:flutter/material.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';
import '../../domain/entities/candidate.dart';

class CandidateDetailPage extends StatelessWidget {
  final Candidate candidate;

  const CandidateDetailPage({super.key, required this.candidate});

  Future<pw.Document> _buildResumePdf() async {
    final pdf = pw.Document();

    pdf.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.all(40),
        build: (context) => [
          pw.Row(
            crossAxisAlignment: pw.CrossAxisAlignment.start,
            children: [
              pw.Expanded(
                child: pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.start,
                  children: [
                    pw.Text(
                      candidate.name,
                      style: pw.TextStyle(
                        fontSize: 28,
                        fontWeight: pw.FontWeight.bold,
                        color: const PdfColor.fromInt(0xFF1565C0),
                      ),
                    ),
                    pw.SizedBox(height: 4),
                    pw.Text(
                      candidate.role,
                      style: pw.TextStyle(
                        fontSize: 16,
                        color: const PdfColor.fromInt(0xFF555555),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          pw.SizedBox(height: 8),
          pw.Divider(color: const PdfColor.fromInt(0xFF1565C0), thickness: 2),
          pw.SizedBox(height: 12),
          pw.Row(
            children: [
              pw.Text(candidate.email,
                  style: const pw.TextStyle(fontSize: 10)),
              pw.SizedBox(width: 16),
              pw.Text(candidate.phone,
                  style: const pw.TextStyle(fontSize: 10)),
              pw.SizedBox(width: 16),
              pw.Text(candidate.location,
                  style: const pw.TextStyle(fontSize: 10)),
            ],
          ),
          pw.SizedBox(height: 16),
          _pdfSection('Professional Summary', [
            pw.Text(
              candidate.summary,
              style: const pw.TextStyle(fontSize: 11),
            ),
          ]),
          _pdfSection('Skills', [
            pw.Wrap(
              spacing: 8,
              runSpacing: 4,
              children: candidate.skills
                  .map((s) => pw.Container(
                        padding: const pw.EdgeInsets.symmetric(
                            horizontal: 8, vertical: 4),
                        decoration: pw.BoxDecoration(
                          color: const PdfColor.fromInt(0xFFE3F2FD),
                          borderRadius:
                              const pw.BorderRadius.all(pw.Radius.circular(4)),
                        ),
                        child: pw.Text(s,
                            style: pw.TextStyle(
                                fontSize: 10,
                                color: const PdfColor.fromInt(0xFF1565C0),
                                fontWeight: pw.FontWeight.bold)),
                      ))
                  .toList(),
            ),
          ]),
          _pdfSection('Experience', [
            pw.Text(
              '${candidate.experience} years of professional experience in ${candidate.role}',
              style: const pw.TextStyle(fontSize: 11),
            ),
            pw.SizedBox(height: 6),
            pw.Text(
              'Most Recent Role: ${candidate.role}',
              style: pw.TextStyle(
                  fontSize: 11, fontWeight: pw.FontWeight.bold),
            ),
            pw.SizedBox(height: 4),
            pw.Text(
              'Responsible for designing, building, and maintaining production systems. '
              'Collaborated with cross-functional teams to deliver high-quality solutions '
              'within agreed timelines.',
              style: const pw.TextStyle(fontSize: 11),
            ),
          ]),
          _pdfSection('Education', [
            pw.Text(
              candidate.education,
              style: pw.TextStyle(
                  fontSize: 11, fontWeight: pw.FontWeight.bold),
            ),
          ]),
        ],
      ),
    );

    return pdf;
  }

  pw.Widget _pdfSection(String title, List<pw.Widget> children) {
    return pw.Column(
      crossAxisAlignment: pw.CrossAxisAlignment.start,
      children: [
        pw.Text(
          title.toUpperCase(),
          style: pw.TextStyle(
            fontSize: 12,
            fontWeight: pw.FontWeight.bold,
            color: const PdfColor.fromInt(0xFF1565C0),
          ),
        ),
        pw.SizedBox(height: 4),
        pw.Divider(color: const PdfColor.fromInt(0xFFBBDEFB)),
        pw.SizedBox(height: 6),
        ...children,
        pw.SizedBox(height: 16),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(candidate.name),
          bottom: const TabBar(
            labelColor: Colors.white,
            unselectedLabelColor: Colors.white70,
            indicatorColor: Colors.white,
            tabs: [
              Tab(icon: Icon(Icons.person_outline), text: 'Profile'),
              Tab(icon: Icon(Icons.picture_as_pdf_outlined), text: 'Resume'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _ProfileTab(candidate: candidate),
            _ResumeTab(buildPdf: _buildResumePdf),
          ],
        ),
      ),
    );
  }
}

class _ProfileTab extends StatelessWidget {
  final Candidate candidate;

  const _ProfileTab({required this.candidate});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ProfileHeader(candidate: candidate),
          const SizedBox(height: 16),
          _InfoCard(
            title: 'Summary',
            child: Text(
              candidate.summary,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            title: 'Contact',
            child: Column(
              children: [
                _InfoRow(Icons.email_outlined, candidate.email),
                const SizedBox(height: 8),
                _InfoRow(Icons.phone_outlined, candidate.phone),
                const SizedBox(height: 8),
                _InfoRow(Icons.location_on_outlined, candidate.location),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            title: 'Skills',
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: candidate.skills
                  .map((s) => Chip(
                        label: Text(s),
                        backgroundColor:
                            const Color(0xFF1565C0).withValues(alpha: 0.1),
                        labelStyle: const TextStyle(
                          color: Color(0xFF1565C0),
                          fontWeight: FontWeight.w600,
                        ),
                        side: const BorderSide(color: Color(0xFF1565C0)),
                      ))
                  .toList(),
            ),
          ),
          const SizedBox(height: 12),
          _InfoCard(
            title: 'Education',
            child: _InfoRow(Icons.school_outlined, candidate.education),
          ),
        ],
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  final Candidate candidate;

  const _ProfileHeader({required this.candidate});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            CircleAvatar(
              radius: 36,
              backgroundColor: const Color(0xFF1565C0),
              child: Text(
                candidate.name[0],
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    candidate.name,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    candidate.role,
                    style: Theme.of(context)
                        .textTheme
                        .bodyMedium
                        ?.copyWith(color: const Color(0xFF1565C0)),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.green.shade100,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '${candidate.experience} yrs experience',
                      style: TextStyle(
                        color: Colors.green.shade800,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  final String title;
  final Widget child;

  const _InfoCard({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: const Color(0xFF1565C0),
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.2,
                  ),
            ),
            const Divider(),
            const SizedBox(height: 4),
            child,
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String text;

  const _InfoRow(this.icon, this.text);

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: Colors.grey.shade600),
        const SizedBox(width: 8),
        Expanded(
          child: Text(text, style: Theme.of(context).textTheme.bodyMedium),
        ),
      ],
    );
  }
}

class _ResumeTab extends StatelessWidget {
  final Future<pw.Document> Function() buildPdf;

  const _ResumeTab({required this.buildPdf});

  @override
  Widget build(BuildContext context) {
    return PdfPreview(
      build: (format) async {
        final doc = await buildPdf();
        return doc.save();
      },
      allowPrinting: true,
      allowSharing: false,
      canChangeOrientation: false,
      canChangePageFormat: false,
      pdfFileName: 'resume.pdf',
    );
  }
}
