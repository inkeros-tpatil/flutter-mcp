import '../../../../core/usecases/usecase.dart';
import '../entities/candidate.dart';
import '../repositories/candidates_repository.dart';

class GetCandidatesUseCase implements UseCase<List<Candidate>, NoParams> {
  final CandidatesRepository repository;

  GetCandidatesUseCase(this.repository);

  @override
  Future<List<Candidate>> call(NoParams params) {
    return repository.getCandidates();
  }
}
