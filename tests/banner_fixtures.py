"""Synthetic Banner-format HTML for structural tests, NOT live catalog evidence.
Only the 74-subject POST request shape is transcribed from supplied screenshots.
All course content in these templates is explicitly test data.
"""
from html import escape
from urllib.parse import urlencode
from prereq.banner import HOST


def detail_url(cid='CS 204', term='202601'):
    subj, num = cid.split()
    return HOST+'/prod/bwckctlg.p_disp_course_detail?'+urlencode([
        ('cat_term_in',term),('subj_code_in',subj),('crse_numb_in',num)])


def page(body,term='202601',title='Catalog Entries'):
    season = ['Fall','Spring','Summer'][int(term[-1])-1]
    year=int(term[:4])
    return f'<html><head><title>{title}</title></head><body><h2>{title}</h2><div>{season} {year}-{year+1}</div>{body}<p>Release: 8.7.2</p></body></html>'


def selector(schedule=False):
    op='bwckgens.p_proc_term_date' if schedule else 'bwckctlg.p_disp_cat_term_date'
    name='p_term' if schedule else 'cat_term_in'
    caller='p_calling_proc' if schedule else 'call_proc_in'
    calling='bwckschd.p_disp_dyn_sched' if schedule else 'bwckctlg.p_disp_dyn_ctlg'
    return f'''<form method="post" action="{HOST}/prod/{op}"><input type="hidden" name="{caller}" value="{calling}">
    <select name="{name}"><option value="202602" selected>Spring 2026-2027</option><option value="202601">Fall 2026-2027</option></select><input type="submit" value="Submit"></form>'''


def search(schedule=False,subjects=('CS','BIO','EE')):
    op='bwckschd.p_get_crse_unsec' if schedule else 'bwckctlg.p_display_courses'
    html=f'<form method="post" action="{HOST}/prod/{op}"><input type="hidden" name="term_in" value="202601"><input type="hidden" name="sel_subj" value="dummy">'
    html+='<select multiple name="sel_subj">'+''.join(f'<option value="{s}">{s}</option>' for s in subjects)+'</select>'
    if schedule:
        html+='<input name="sel_crse" value=""><input name="sel_title" value=""><input type="hidden" name="sel_schd" value="dummy"><select name="sel_schd"><option value="%">All</option></select>'
    return html+'</form>'


def listing(cids=('CS 204','EE 302'),term='202601',embedded=False):
    blocks=[]
    for cid in cids:
        body=f'<tr><th class="ddtitle"><a href="{escape(detail_url(cid,term))}">{cid} - Test title [ Syllabus ]</a></th></tr><tr><td class="dddefault">Test description.<br>3.000 Credit hours<br><b>Levels:</b> Undergraduate<br><b>Course Attributes:</b> 6 ECTS'
        if embedded:
            body+='<p><b>Prerequisites:</b> Undergraduate level CS 201 Minimum Grade of D</p><p><b>Corequisites:</b> CS 204L</p>'
        blocks.append(body+'</td></tr>')
    return page('<table>'+''.join(blocks)+'</table>',term)


def detail(cid='CS 204',term='202601',prereq='Undergraduate level CS 201 Minimum Grade of D',coreq='CS 204L',general=None):
    body=f'<table><tr><th class="ddtitle">{cid} - Test title</th></tr><tr><td>Test description. 3.000 Credit hours<br>6 ECTS'
    if prereq is not None: body+='<p><b>Prerequisites:</b> '+escape(prereq)+'</p>'
    if coreq is not None: body+='<p><b>Corequisites:</b> '+escape(coreq)+'</p>'
    if general is not None: body+='<p><b>General Requirements:</b> '+escape(general)+'</p>'
    return page(body+'</td></tr></table>',term,'Catalog Entry')


def schedule(cid='CS 204',term='202601',crn='10001',empty=False):
    if empty: return page('No classes were found that meet your search criteria.',term,'Class Schedule Listing')
    url=HOST+'/prod/bwckschd.p_disp_detail_sched?'+urlencode({'term_in':term,'crn_in':crn})
    body=f'<table><tr><th class="ddtitle"><a href="{escape(url)}">Test course - {crn} - {cid} - A</a></th></tr><tr><td><table><tr><th>Type</th><th>Time</th><th>Days</th><th>Where</th><th>Date Range</th><th>Schedule Type</th><th>Instructors</th></tr><tr><td>Class</td><td>10:40 am - 12:30 pm</td><td>TR</td><td>FENS G001</td><td>Sep 21 - Jan 8</td><td>Lecture</td><td>Test instructor</td></tr></table></td></tr></table>'
    return page(body,term,'Class Schedule Listing')
