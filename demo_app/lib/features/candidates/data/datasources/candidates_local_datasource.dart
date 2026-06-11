import '../models/candidate_model.dart';

abstract class CandidatesLocalDataSource {
  Future<List<CandidateModel>> getCandidates();
}

class CandidatesLocalDataSourceImpl implements CandidatesLocalDataSource {
  @override
  Future<List<CandidateModel>> getCandidates() async {
    await Future.delayed(const Duration(milliseconds: 300));
    return const [
      CandidateModel(
        id: 1,
        name: 'John Smith',
        role: 'Senior Software Engineer',
        email: 'john.smith@email.com',
        phone: '+1 (555) 123-4567',
        location: 'San Francisco, CA',
        experience: 7,
        skills: ['Flutter', 'Dart', 'React', 'Node.js', 'AWS'],
        education: 'B.S. Computer Science, Stanford University',
        summary:
            'Passionate software engineer with 7 years of experience building scalable mobile and web applications. Strong background in cross-platform development and cloud architecture.',
      ),
      CandidateModel(
        id: 2,
        name: 'Emily Johnson',
        role: 'Product Manager',
        email: 'emily.johnson@email.com',
        phone: '+1 (555) 234-5678',
        location: 'New York, NY',
        experience: 5,
        skills: ['Product Strategy', 'Agile', 'Jira', 'Analytics', 'SQL'],
        education: 'MBA, Harvard Business School',
        summary:
            'Results-driven product manager with 5 years of experience leading cross-functional teams. Expert in translating business requirements into technical roadmaps and delivering products on time.',
      ),
      CandidateModel(
        id: 3,
        name: 'Michael Davis',
        role: 'UI/UX Designer',
        email: 'michael.davis@email.com',
        phone: '+1 (555) 345-6789',
        location: 'Austin, TX',
        experience: 4,
        skills: ['Figma', 'Adobe XD', 'Prototyping', 'User Research', 'CSS'],
        education: 'B.F.A. Graphic Design, Rhode Island School of Design',
        summary:
            'Creative UI/UX designer with a strong portfolio across mobile, web, and SaaS platforms. Specialises in user-centred design and accessibility standards.',
      ),
      CandidateModel(
        id: 4,
        name: 'Sarah Wilson',
        role: 'Data Scientist',
        email: 'sarah.wilson@email.com',
        phone: '+1 (555) 456-7890',
        location: 'Seattle, WA',
        experience: 6,
        skills: ['Python', 'Machine Learning', 'TensorFlow', 'SQL', 'Tableau'],
        education: 'M.S. Data Science, University of Washington',
        summary:
            'Data scientist with 6 years of experience building predictive models and deriving actionable insights. Proven track record of reducing churn and improving revenue through data-driven decisions.',
      ),
      CandidateModel(
        id: 5,
        name: 'Robert Brown',
        role: 'DevOps Engineer',
        email: 'robert.brown@email.com',
        phone: '+1 (555) 567-8901',
        location: 'Chicago, IL',
        experience: 8,
        skills: ['Docker', 'Kubernetes', 'CI/CD', 'Terraform', 'Linux'],
        education: 'B.S. Information Technology, University of Illinois',
        summary:
            'Senior DevOps engineer with 8 years of expertise in cloud infrastructure, automation, and reliability engineering. Led migration of legacy monolith to microservices for a Fortune 500 company.',
      ),
    ];
  }
}
