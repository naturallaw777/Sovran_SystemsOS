# Contributing to Sovran Systems OS

First off, thank you for considering contributing to Sovran_SystemsOS! 🎉

## Development and Release Repositories

The GitHub repository is the primary location for Sovran_SystemsOS development
and collaboration and serves as the project's connection to the GitHub
ecosystem. Most work is contributed through feature branches and pull requests
that target GitHub `main`. Development may also begin in a local branch or on
`staging-dev` at the project's self-hosted Gitea instance:
https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS.

GitHub `main` and Gitea `staging-dev` are kept synchronized as the active
development line, although one may briefly lead the other while changes are
being integrated. The canonical, release-ready code is maintained on Gitea's
[`stable` branch](https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/src/branch/stable),
in keeping with the self-sovereignty ethos of Sovran_SystemsOS.

The workflow is:

1. Most development and project collaboration — including issues, pull
   requests, and reviews — happens through GitHub, with completed work
   integrated into `main`.
2. Work may also originate locally or on Gitea `staging-dev`. Accepted changes
   are synchronized between GitHub `main` and Gitea `staging-dev`.
3. When changes are complete and tested, they are promoted to Gitea `stable`,
   which is the code used by released Sovran_SystemsOS builds.

Please note: GitHub `main` and Gitea `staging-dev` may contain new features and
code not yet in `stable`, and that code may not be fully tested.

Moreover, Sovran_SystemsOS has been improved with the help of AI. We have used Copilot and Arean.Ai to work through significant coding challenges and troubleshooting hurdles. We will continue to use AI to help keep Sovran_SystemsOS stable and maintained.

## How Can I Contribute?

### 🐛 Reporting Bugs
- Open an [Issue](https://github.com/naturallaw777/Sovran_SystemsOS/issues)
- Use a clear and descriptive title
- Describe the steps to reproduce the bug
- Include your OS version, hardware specs, and any relevant logs

### 💡 Suggesting Features
- Open an [Issue](https://github.com/naturallaw777/Sovran_SystemsOS/issues) with the tag `enhancement`
- Explain the feature and why it would be useful
- Be as detailed as possible

### 🔧 Submitting Code Changes

#### 1. Fork the Repository
Click the "Fork" button at the top right of the GitHub repository.

#### 2. Clone Your Fork
```bash
git clone https://github.com/YOUR_USERNAME/Sovran_SystemsOS.git
cd Sovran_SystemsOS
```

#### 3. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

#### 4. Make Your Changes
- Write clean, well-commented code
- Follow the existing code style and structure
- Test your changes thoroughly

#### 5. Commit Your Changes
```bash
git add .
git commit -m "Brief description of your changes"
```

#### 6. Push to Your Fork
```bash
git push origin feature/your-feature-name
```

#### 7. Open a Pull Request
- Go to the original repository on GitHub
- Click "New Pull Request"
- Select your fork and branch
- Provide a clear title and description of your changes
- Reference any related Issues (e.g., "Closes #12")

## Pull Request Guidelines

- **One PR per feature/fix.** Do not bundle unrelated changes.
- **Keep PRs small and focused.** Smaller PRs are easier to review and merge.
- **Write meaningful commit messages.**
- **Do not push directly to `main`.** Always use a feature branch and open a PR.
- **Be patient.** PRs will be reviewed as soon as possible.

## Code Style

- Follow the existing patterns in the codebase
- Comment your code where necessary
- Keep functions small and focused

## Code of Conduct

By participating in this project, you agree to be respectful and constructive.
We are building something meaningful — let's do it together with integrity.

