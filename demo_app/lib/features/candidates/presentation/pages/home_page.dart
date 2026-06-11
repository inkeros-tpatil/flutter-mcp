import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/routes/app_router.dart';
import '../../domain/entities/candidate.dart';
import '../bloc/candidates_bloc.dart';
import '../bloc/candidates_event.dart';
import '../bloc/candidates_state.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  @override
  void initState() {
    super.initState();
    context.read<CandidatesBloc>().add(LoadCandidates());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Candidates'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => Navigator.pushReplacementNamed(
              context,
              AppRouter.login,
            ),
          ),
        ],
      ),
      body: BlocBuilder<CandidatesBloc, CandidatesState>(
        builder: (context, state) {
          if (state is CandidatesLoading) {
            return const Center(child: CircularProgressIndicator());
          } else if (state is CandidatesLoaded) {
            return _CandidatesTable(candidates: state.candidates);
          } else if (state is CandidatesError) {
            return Center(child: Text(state.message));
          }
          return const SizedBox.shrink();
        },
      ),
    );
  }
}

class _CandidatesTable extends StatelessWidget {
  final List<Candidate> candidates;

  const _CandidatesTable({required this.candidates});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${candidates.length} Candidates',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: Colors.grey.shade600),
          ),
          const SizedBox(height: 12),
          Card(
            elevation: 2,
            clipBehavior: Clip.antiAlias,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                headingRowColor: WidgetStateProperty.all(
                  const Color(0xFF1565C0).withValues(alpha: 0.08),
                ),
                columns: const [
                  DataColumn(label: Text('#')),
                  DataColumn(label: Text('Name')),
                  DataColumn(label: Text('Role')),
                  DataColumn(label: Text('Location')),
                  DataColumn(label: Text('Experience')),
                ],
                rows: candidates.map((c) {
                  return DataRow(
                    onSelectChanged: (_) {
                      Navigator.pushNamed(
                        context,
                        AppRouter.candidateDetail,
                        arguments: c,
                      );
                    },
                    cells: [
                      DataCell(Text('${c.id}')),
                      DataCell(
                        Row(
                          children: [
                            CircleAvatar(
                              radius: 16,
                              backgroundColor: const Color(0xFF1565C0),
                              child: Text(
                                c.name[0],
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(c.name),
                          ],
                        ),
                      ),
                      DataCell(Text(c.role)),
                      DataCell(Text(c.location)),
                      DataCell(Text('${c.experience} yrs')),
                    ],
                  );
                }).toList(),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Tap a row to view candidate details',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: Colors.grey),
          ),
        ],
      ),
    );
  }
}
