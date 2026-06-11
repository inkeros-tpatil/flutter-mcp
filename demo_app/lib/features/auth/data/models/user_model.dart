import '../../domain/entities/user.dart';

class UserModel extends User {
  const UserModel({required super.username});

  factory UserModel.fromEntity(User user) => UserModel(username: user.username);
}
