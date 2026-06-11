import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/usecases/usecase.dart';
import '../../domain/usecases/get_candidates_usecase.dart';
import 'candidates_event.dart';
import 'candidates_state.dart';

class CandidatesBloc extends Bloc<CandidatesEvent, CandidatesState> {
  final GetCandidatesUseCase getCandidatesUseCase;

  CandidatesBloc(this.getCandidatesUseCase) : super(CandidatesInitial()) {
    on<LoadCandidates>(_onLoadCandidates);
  }

  Future<void> _onLoadCandidates(
    LoadCandidates event,
    Emitter<CandidatesState> emit,
  ) async {
    emit(CandidatesLoading());
    try {
      final candidates = await getCandidatesUseCase(NoParams());
      emit(CandidatesLoaded(candidates));
    } catch (e) {
      emit(const CandidatesError('Failed to load candidates'));
    }
  }
}
