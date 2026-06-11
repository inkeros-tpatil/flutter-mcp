import '../../domain/entities/candidate.dart';
import '../../domain/repositories/candidates_repository.dart';
import '../datasources/candidates_local_datasource.dart';

class CandidatesRepositoryImpl implements CandidatesRepository {
  final CandidatesLocalDataSource dataSource;

  CandidatesRepositoryImpl(this.dataSource);

  @override
  Future<List<Candidate>> getCandidates() {
    return dataSource.getCandidates();
  }
}
