import '../entities/candidate.dart';

abstract class CandidatesRepository {
  Future<List<Candidate>> getCandidates();
}
