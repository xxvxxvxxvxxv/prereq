"""Representative, reconstructed HTML fixtures, NOT archived upstream responses."""
from html import escape
from urllib.parse import urlencode
from prereq.catalog import degree_url,course_url

def row(cid,title='Test course',ects=6,credits=3,faculty='FENS'):
    url=escape(course_url(cid),quote=True)
    return f'<tr><td>*</td><td><a href="{url}">{cid}</a></td><td><a href="{url}">{title}</a></td><td>{ects}</td><td>{credits}</td><td>{faculty}</td></tr>'

def terms(program='BSCS',term='202401'):
    return f'<form><select name="P_TERM"><option value="{term}">{term}</option></select></form><a href="{escape(degree_url(program,term),quote=True)}">{term}</a>'

def pool_url(program,term,cat):
    # Deliberately avoid EE suffix conventions: code must discover, not guess.
    return 'https://suis.sabanciuniv.edu/prod/SU_DEGREE.p_list_courses?'+urlencode(dict(P_AREA=program+'_'+{'core':'CUSTOM1','area':'AEL','free':'CUSTOM3'}[cat],P_LANG='EN',P_LEVEL='UG',P_PROGRAM=program,P_TERM=term))

def degree(program='BSCS',term='202401'):
    cats=[('University Courses','university',41),('Required Courses','required',33),('Core Electives','core',25),('Area Electives','area',9),('Free Electives','free',15)]
    html=f'<html><body><h3>Admit Term: Fall 2024-2025</h3><h1>UNDERGRADUATE PROGRAM ({program})</h1><table>'
    for label,key,credits in cats:
        html+=f'<tr><td><a href="#{key}">{label}</a></td><td>-</td><td>{credits}</td><td>-</td></tr>'
    html+='<tr><td>Total</td><td>240</td><td>125</td><td>-</td></tr></table>'
    for label,key,_ in cats:
        html+=f'<h2>{label}</h2><p>Rule for {key}: review choices before registration.</p>'
        if key=='university':
            html+='<table>'+row('MATH 101','Calculus I')+'</table>'
        elif key=='required':
            html+='<table>'+row('CS 303','Logic and Digital System Design',7,4)+'</table>'
        else:
            html+=f'<p><a href="{escape(pool_url(program,term,key),quote=True)}">Click</a> For {label}</p>'
    html+='<h2>Faculty Courses</h2><p>Faculty courses overlap other requirements.</p></body></html>'
    return html

def pool(program='BSCS',cid='CS 201'):
    return f'<h1>UNDERGRADUATE PROGRAM ({program})</h1><h2>Electives</h2><table><tr><th></th><th>Course</th><th>Name</th><th>ECTS Credits</th><th>SU Credits</th><th>Faculty</th></tr>{row(cid)}</table>'

def course(cid='EE 202',prereq='ENS 203 - Undergraduate - Min Grade D',coreq='EE 200 and EE 202R'):
    return f'<table><tr><td><b>{cid} Electronic Circuits II</b></td><td>3 Credits</td></tr></table><p>Course description not used.</p><table><tr><td>Last Offered Terms</td><td>Course Name</td><td>SU Credit</td></tr><tr><td>Fall 2026-2027</td><td>Example</td><td>3</td></tr></table><p>Prerequisite: {escape(prereq)}</p><p>Corequisite: {escape(coreq)}</p><p>ECTS Credit: 6 ECTS (ENGINEERING:6 / BASIC:0)</p><p>General Requirements:</p>'
