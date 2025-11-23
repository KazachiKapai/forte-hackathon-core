import gitlab

# https://gitlab.com/abdigal.2015/banking-system#
gl = gitlab.Gitlab("https://gitlab.com", private_token="glpat-rvpjWsjGbPEN4hAAUiOCQ286MQp1Oml4bHVwCw.01.120ko7p0a")

projects = gl.projects.list(membership=True)

mr = projects[0].mergerequests.list()

diffs = mr[0].diffs.list()

diff = mr[0].diffs.get(diffs[0].get_id())

for d in diff.diffs:
    print("update: ", d['new_path'], d['diff'])